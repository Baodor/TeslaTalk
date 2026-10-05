"""Atomic account deletion, including trip dependencies and access revocation."""
import time
from fastapi import HTTPException
from . import db


def delete_user(user_id, confirmed_username):
    with db.connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        user = connection.execute('SELECT username FROM users WHERE id=?',(user_id,)).fetchone()
        if not user:
            raise HTTPException(404,'Benutzer nicht gefunden.')
        if user['username'] != confirmed_username:
            raise HTTPException(409,'Zur Bestätigung den aktuellen Benutzernamen exakt eingeben.')
        owned = [row['id'] for row in connection.execute('SELECT id FROM trips WHERE leader_id=?',(user_id,))]
        # QR identities belong to a trip. Remove orphaned identities with its deletion,
        # while retaining an identity that still belongs to another group.
        guests = [row['user_id'] for row in connection.execute("SELECT DISTINCT p.user_id FROM passengers p JOIN users u ON u.id=p.user_id JOIN trips t ON t.id=p.trip_id WHERE t.leader_id=? AND u.provider='guest' AND NOT EXISTS (SELECT 1 FROM members m JOIN trips other ON other.id=m.trip_id WHERE m.user_id=p.user_id AND other.leader_id!=?)",(user_id,user_id))]
        removed = list(dict.fromkeys([user_id,*guests]))
        remaining = set()
        deadline = time.time()+125  # Existing self-hosted LiveKit join tokens live <=120 s.
        for uid in removed:
            connection.execute('DELETE FROM control_batches WHERE leader_id=? OR trip_id IN (SELECT trip_id FROM members WHERE user_id=?)',(uid,uid))
            for row in connection.execute('SELECT trip_id FROM members WHERE user_id=?',(uid,)):
                if row['trip_id'] not in owned:
                    remaining.add(row['trip_id'])
                    connection.execute('INSERT INTO voice_removals VALUES (?,?,?) ON CONFLICT(trip_id,user_id) DO UPDATE SET expires_at=excluded.expires_at',(row['trip_id'],uid,deadline))
            connection.execute('DELETE FROM push_outbox WHERE user_id=?',(uid,))
            connection.execute('DELETE FROM push_subscriptions WHERE user_id=?',(uid,))
            # OIDC admins have an independent identity namespace.
            connection.execute("DELETE FROM sessions WHERE user_id=? AND kind='user'",(uid,))
            connection.execute('DELETE FROM friendships WHERE low_id=? OR high_id=? OR requester=?',(uid,uid,uid))
            for table in ('credentials','api_keys','invites','passengers','messages','samples','personal_locations','route_followers','control_grants'):
                connection.execute(f'DELETE FROM {table} WHERE user_id=?',(uid,))
            connection.execute('DELETE FROM trip_navigation WHERE trip_id IN (SELECT trip_id FROM trip_planners WHERE user_id=?) OR vehicle_id IN (SELECT id FROM vehicles WHERE user_id=?)',(uid,uid))
            connection.execute('DELETE FROM trip_planners WHERE user_id=? OR vehicle_id IN (SELECT id FROM vehicles WHERE user_id=?)',(uid,uid))
            connection.execute('DELETE FROM route_followers WHERE vehicle_id IN (SELECT id FROM vehicles WHERE user_id=?)',(uid,))
            connection.execute('UPDATE users SET favorite_vehicle=NULL WHERE favorite_vehicle IN (SELECT id FROM vehicles WHERE user_id=?)',(uid,))
            connection.execute('UPDATE members SET vehicle_id=NULL WHERE vehicle_id IN (SELECT id FROM vehicles WHERE user_id=?)',(uid,))
            connection.execute('DELETE FROM members WHERE user_id=?',(uid,))
            connection.execute('DELETE FROM vehicles WHERE user_id=?',(uid,))
        for trip_id in owned:
            connection.execute('INSERT INTO voice_room_deletions VALUES (?,?) ON CONFLICT(trip_id) DO UPDATE SET expires_at=excluded.expires_at',(trip_id,deadline))
            for table in ('push_outbox','route_followers','trip_navigation','trip_planners','control_batches','control_grants','invites','passengers','messages','samples','personal_locations','members'):
                connection.execute(f'DELETE FROM {table} WHERE trip_id=?',(trip_id,))
            connection.execute('DELETE FROM trips WHERE id=?',(trip_id,))
        for uid in removed:
            connection.execute('DELETE FROM users WHERE id=?',(uid,))
        assert not connection.execute('PRAGMA foreign_key_check').fetchall()
    return {'user_ids':removed,'owned_trip_ids':owned,'remaining_trip_ids':sorted(remaining)}
