def ranking(rows):
    groups = {}
    for row in rows:
        groups.setdefault(row['user_id'], []).append(row)
    output = []
    for user_id, samples in groups.items():
        samples.sort(key=lambda x:x['captured_at'])
        odometer_samples = [r for r in samples if r.get('odometer_km') is not None]
        odometers = [r['odometer_km'] for r in odometer_samples]
        paired = [r for r in samples if r.get('odometer_km') is not None and r.get('energy_used_kwh') is not None]
        energies = [r['energy_used_kwh'] for r in paired]
        # Cumulative measured counters only. SOC percentages are not energy measurements.
        distance = odometers[-1]-odometers[0] if len(odometers)>=2 and all(b>=a for a,b in zip(odometers,odometers[1:])) else None
        used = energies[-1]-energies[0] if len(energies)>=2 and all(b>=a for a,b in zip(energies,energies[1:])) else None
        energy_distance = paired[-1]['odometer_km']-paired[0]['odometer_km'] if len(paired)>=2 and distance is not None else None
        observed_seconds = odometer_samples[-1]['captured_at']-odometer_samples[0]['captured_at'] if len(odometer_samples)>=2 else 0
        seconds = samples[-1]['captured_at']-samples[0]['captured_at']
        output.append({'user_id':user_id, 'distance_km':round(distance,2) if distance is not None else None,
                       'duration_seconds':round(seconds),
                       'average_speed_kmh':round(distance/observed_seconds*3600,1) if distance is not None and observed_seconds>0 else None,
                       'consumption_kwh_100km':round(used/energy_distance*100,2) if energy_distance and energy_distance>=1 and used is not None else None,
                       'samples':len(samples)})
    return sorted(output, key=lambda r:(r['consumption_kwh_100km'] is None, r['consumption_kwh_100km'] or 0))
