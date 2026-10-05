"""Automatic in-trip route visibility and owner-approved destination commands."""
import asyncio
import hashlib
import json
import math
import time
import httpx
from fastapi import HTTPException
from pydantic import BaseModel, Field
from . import db, fleet, push
from .navigation import empty_navigation
from .realtime import hub

locks = {}


class RoutePlan(BaseModel):
    planner_user_id: str = Field(min_length=1,max_length=80)
    destination: str = Field(min_length=1,max_length=200)


class RouteProblem(BaseModel):
    reason: str = Field(pattern='^(different_route|cannot_follow)$')


def lock(trip_id):
    return locks.setdefault(trip_id,asyncio.Lock())


def active(trip_id):
    trip = db.one('SELECT * FROM trips WHERE id=?',(trip_id,))
    if not trip or trip['finished_at'] or not trip['starts_at'] <= time.time() < trip['ends_at']:
        raise HTTPException(403,'Routensteuerung ist nur während der aktiven Fahrt möglich.')
    return trip


def planner_id(trip):
    row = db.one("SELECT p.user_id FROM trip_planners p JOIN members m ON m.trip_id=p.trip_id AND m.user_id=p.user_id AND m.vehicle_id=p.vehicle_id WHERE p.trip_id=? AND m.role='driver' AND m.left_at IS NULL",(trip['id'],))
    return row['user_id'] if row else None


def car(trip_id,user_id):
    row = db.one("SELECT v.*,u.provider FROM members m JOIN vehicles v ON v.id=m.vehicle_id AND v.user_id=m.user_id JOIN users u ON u.id=m.user_id WHERE m.trip_id=? AND m.user_id=? AND m.role='driver' AND m.left_at IS NULL",(trip_id,user_id))
    if not row:
        raise HTTPException(404,'Fahrzeug ist kein aktives Fahrerfahrzeug dieser Fahrt.')
    return row


def consent(trip_id,user_id,vehicle_id):
    return db.one('SELECT * FROM route_followers WHERE trip_id=? AND user_id=? AND vehicle_id=?',(trip_id,user_id,vehicle_id))


def snapshot(trip):
    """Cached visibility is automatic; this never sends a command or HTTP read."""
    old = db.one('SELECT * FROM trip_navigation WHERE trip_id=?',(trip['id'],))
    if trip['finished_at'] or time.time() >= trip['ends_at']:
        return json.loads(old['data']) if old else None
    if time.time() < trip['starts_at']:
        return None
    if planner_id(trip) is None:
        return None
    try:
        vehicle = car(trip['id'],planner_id(trip))
    except HTTPException:
        return json.loads(old['data']) if old else None
    navigation = json.loads(vehicle['data']).get('navigation')
    if vehicle['provider'] == 'demo' and not navigation:
        navigation = fleet.demo_navigation()
    pending = consent(trip['id'],planner_id(trip),vehicle['id'])
    if pending and pending['sent_at'] and navigation and navigation['updated_at'] < pending['sent_at']:
        navigation = None
    if navigation and (not old or old['vehicle_id'] != vehicle['id'] or json.loads(old['data'])['updated_at'] <= navigation['updated_at']):
        db.execute('INSERT INTO trip_navigation VALUES (?,?,?) ON CONFLICT(trip_id) DO UPDATE SET vehicle_id=excluded.vehicle_id,data=excluded.data',(trip['id'],vehicle['id'],json.dumps(navigation)))
        return navigation
    return json.loads(old['data']) if old and old['vehicle_id'] == vehicle['id'] else None


def overview(trip):
    selected = planner_id(trip)
    rows = db.all_rows("SELECT u.id AS user_id,u.display_name,m.vehicle_id,v.name AS vehicle_name,v.model,v.data FROM members m JOIN users u ON u.id=m.user_id JOIN vehicles v ON v.id=m.vehicle_id AND v.user_id=m.user_id WHERE m.trip_id=? AND m.role='driver' AND m.left_at IS NULL",(trip['id'],))
    for row in rows:
        cached = json.loads(row.pop('data'))
        measured = db.one("SELECT battery_pct,range_km,captured_at AS updated_at FROM samples WHERE trip_id=? AND user_id=? AND source!='browser' ORDER BY id DESC LIMIT 1",(trip['id'],row['user_id']))
        if not trip['finished_at'] and time.time() < trip['ends_at'] and (not measured or (cached.get('updated_at') or 0) > measured['updated_at']):
            measured = {key:cached.get(key) for key in ('battery_pct','range_km','updated_at')}
        row.update(measured or {'battery_pct':None,'range_km':None,'updated_at':None})
        following = consent(trip['id'],row['user_id'],row['vehicle_id'])
        row.update(accepted=bool(following),status=following['status'] if following else 'not_accepted',problem=following['problem'] if following else None,
                   can_plan=row['user_id'] == trip['leader_id'] or bool(following),is_planner=row['user_id'] == selected)
    fresh = [row for row in rows if row['updated_at'] is not None and time.time()-row['updated_at'] <= 300]
    def minimum(field):
        known = [row for row in fresh if row[field] is not None]
        return min(known,key=lambda row:row[field])['user_id'] if known else None
    return {'planner_user_id':selected,'vehicles':rows,'transfer_mode':'destination_only','comparison_tolerance_m':200,
            'recommendations':{'lowest_battery_user_id':minimum('battery_pct'),'lowest_range_user_id':minimum('range_km')},
            'charging_stops_confirmed':False}


def target(nav):
    if nav['destination_latitude'] is not None and nav['destination_longitude'] is not None:
        return f"{nav['destination_latitude']:.6f}, {nav['destination_longitude']:.6f}"
    return nav['destination'] or ''


def distance(a,b):
    lat = math.radians((a[0]+b[0])/2)
    return math.hypot((a[0]-b[0])*111_195,(a[1]-b[1])*111_195*math.cos(lat))


def compare(reference, actual, sent_at):
    if not actual or actual['updated_at'] < (sent_at or 0) or time.time()-actual['updated_at'] > 300:
        return 'unconfirmed',None
    if actual['status'] != 'active':
        return 'unconfirmed',None  # a missing response is not a proven route mismatch
    if actual['battery_arrival_pct'] is not None and actual['battery_arrival_pct'] < 0:
        return 'different','insufficient_battery'
    ref_goal = (reference['destination_latitude'],reference['destination_longitude'])
    actual_goal = (actual['destination_latitude'],actual['destination_longitude'])
    if None not in ref_goal+actual_goal and distance(ref_goal,actual_goal) > 200:
        return 'different','different_route'
    first, second = reference['route_points'],actual['route_points']
    if len(first) < 2 or len(second) < 2:
        return 'unconfirmed',None
    # Different approach positions cannot establish a comparable whole route.
    if distance(first[0],second[0]) > 1000:
        return 'unconfirmed',None
    if first == second:
        return 'matching',None
    # Bounded geometry comparison; interpolate distance to segments rather than
    # mistaking different polyline sampling for a different road.
    def sampled(points):
        step = max(1,math.ceil(len(points)/300))
        return points[::step]+([points[-1]] if points[-1] != points[::step][-1] else [])
    def near_segment(point,start,end):
        scale = math.cos(math.radians(point[0]))
        a = ((start[0]-point[0])*111195,(start[1]-point[1])*111195*scale)
        b = ((end[0]-point[0])*111195,(end[1]-point[1])*111195*scale)
        dx,dy = b[0]-a[0],b[1]-a[1]
        fraction = max(0,min(1,-(a[0]*dx+a[1]*dy)/(dx*dx+dy*dy))) if dx or dy else 0
        return math.hypot(a[0]+fraction*dx,a[1]+fraction*dy)
    a,b = sampled(first),sampled(second)
    for points,other in ((a,b),(b,a)):
        for point in points:
            if min(near_segment(point,start,end) for start,end in zip(other,other[1:])) > 200:
                return 'different','different_route'
    return 'matching',None


def notify_problem(trip,user_id,problem):
    row = db.one('SELECT notified_problem FROM route_followers WHERE trip_id=? AND user_id=?',(trip['id'],user_id))
    if row and row['notified_problem'] != problem:
        db.execute('UPDATE route_followers SET notified_problem=? WHERE trip_id=? AND user_id=?',(problem,trip['id'],user_id))
        if problem and user_id != trip['leader_id']:
            push.enqueue(trip['leader_id'],'Eine übernommene Fahrzeugroute weicht ab oder kann nicht gefahren werden. Bitte Routenübersicht prüfen.','/trip/'+trip['id'],'route-problem-'+trip['id'],trip['id'])


async def broadcast(trip):
    await hub.broadcast(trip['id'],{'type':'navigation','navigation':snapshot(trip),'route_overview':overview(trip)})


async def distribute(trip):
    nav = snapshot(trip)
    if not nav or nav['status'] != 'active' or time.time()-nav['updated_at'] > 300:
        await broadcast(trip)
        return
    db.execute("UPDATE route_followers SET status='source_ready' WHERE trip_id=? AND user_id=? AND status='planning'",(trip['id'],planner_id(trip)))
    destination = target(nav)
    command_key = hashlib.sha256(destination.encode()).hexdigest()
    for following in db.all_rows('SELECT * FROM route_followers WHERE trip_id=?',(trip['id'],)):
        if following['user_id'] == planner_id(trip):
            continue
        try:
            current = active(trip['id'])
            vehicle = car(trip['id'],following['user_id'])
            if vehicle['id'] != following['vehicle_id'] or not consent(trip['id'],following['user_id'],vehicle['id']):
                continue
            if following['command_key'] != command_key:
                sent_at = time.time()
                db.execute("UPDATE route_followers SET command_key=?,sent_at=?,status='sending',problem=NULL WHERE trip_id=? AND user_id=?",(command_key,sent_at,trip['id'],following['user_id']))
                await fleet.send_navigation(following['user_id'],vehicle,destination,trip['id'])
                active(trip['id'])
                db.execute("UPDATE route_followers SET status='unconfirmed' WHERE trip_id=? AND user_id=?",(trip['id'],following['user_id']))
                following['sent_at'] = sent_at
            if following['status'] == 'error' and following['command_key'] == command_key:
                continue  # no repeated command storm; owner can explicitly retry
            actual = json.loads(car(trip['id'],following['user_id'])['data']).get('navigation')
            status,problem = compare(nav,actual,following['sent_at'])
            # Explicit "cannot follow" reports persist until owner accepts again.
            old = consent(trip['id'],following['user_id'],vehicle['id'])
            if old and old['problem'] == 'cannot_follow':
                status,problem = 'different','cannot_follow'
            db.execute('UPDATE route_followers SET status=?,problem=? WHERE trip_id=? AND user_id=?',(status,problem,trip['id'],following['user_id']))
            notify_problem(current,following['user_id'],problem)
        except (HTTPException,httpx.HTTPError) as error:
            # Never log or expose Tesla token/provider bodies. The driver sees a
            # controlled status and can retry; do not assert in-car acceptance.
            if isinstance(error,HTTPException) and error.status_code == 403:
                continue
            db.execute("UPDATE route_followers SET status='error',problem='command_error' WHERE trip_id=? AND user_id=?",(trip['id'],following['user_id']))
    await broadcast(trip)


async def observe(vehicle_id,user_id,navigation):
    now = time.time()
    trips = db.all_rows('SELECT t.* FROM trips t JOIN members m ON m.trip_id=t.id WHERE m.user_id=? AND m.vehicle_id=? AND m.left_at IS NULL AND t.starts_at<=? AND t.ends_at>? AND t.finished_at IS NULL',(user_id,vehicle_id,now,now))
    for trip in trips:
        async with lock(trip['id']):
            try:
                trip = active(trip['id'])
                if car(trip['id'],user_id)['id'] != vehicle_id:
                    continue
            except HTTPException:
                continue
            if planner_id(trip) == user_id:
                old = db.one('SELECT * FROM trip_navigation WHERE trip_id=?',(trip['id'],))
                if not old or json.loads(old['data'])['updated_at'] <= navigation['updated_at'] or old['vehicle_id'] != vehicle_id:
                    pending = consent(trip['id'],user_id,vehicle_id)
                    if not pending or not pending['sent_at'] or navigation['updated_at'] >= pending['sent_at']:
                        db.execute('INSERT INTO trip_navigation VALUES (?,?,?) ON CONFLICT(trip_id) DO UPDATE SET vehicle_id=excluded.vehicle_id,data=excluded.data',(trip['id'],vehicle_id,json.dumps(navigation)))
            await distribute(trip)
