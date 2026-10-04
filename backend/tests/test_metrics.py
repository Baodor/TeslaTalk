from app.metrics import ranking
from app.fleet import normalize


def test_measured_energy_required_for_consumption():
    rows=[{'user_id':'a','captured_at':0,'odometer_km':100,'battery_pct':90},
          {'user_id':'a','captured_at':3600,'odometer_km':200,'battery_pct':70}]
    result=ranking(rows)[0]
    assert result['consumption_kwh_100km'] is None
    assert result['distance_km']==100
    assert result['average_speed_kmh']==100


def test_cumulative_counters_and_reset():
    rows=[{'user_id':'a','captured_at':0,'odometer_km':100,'energy_used_kwh':1000},
          {'user_id':'a','captured_at':3600,'odometer_km':200,'energy_used_kwh':1015},
          {'user_id':'b','captured_at':0,'odometer_km':100,'energy_used_kwh':2000},
          {'user_id':'b','captured_at':3600,'odometer_km':200,'energy_used_kwh':1}]
    result=ranking(rows)
    assert result[0]['consumption_kwh_100km']==15
    assert result[1]['consumption_kwh_100km'] is None


def test_fleet_units_converted():
    result=normalize({'drive_state':{'latitude':50,'longitude':8,'speed':50},'charge_state':{'battery_level':70,'battery_range':200},'vehicle_state':{'odometer':1000}})
    assert result['speed_kmh']==80.5
    assert result['range_km']==321.9
    assert result['odometer_km']==1609.344


def test_counter_reset_in_middle_invalidates_metric():
    rows=[{'user_id':'a','captured_at':i,'odometer_km':100+i,'energy_used_kwh':value} for i,value in enumerate([1000,5,1010])]
    assert ranking(rows)[0]['consumption_kwh_100km'] is None


def test_energy_and_distance_use_same_measurement_interval():
    rows=[{'user_id':'a','captured_at':0,'odometer_km':100},
          {'user_id':'a','captured_at':1000,'odometer_km':150,'energy_used_kwh':1000},
          {'user_id':'a','captured_at':2000,'odometer_km':200,'energy_used_kwh':1007.5},
          {'user_id':'a','captured_at':3000,'odometer_km':300}]
    result=ranking(rows)[0]
    assert result['distance_km']==200
    assert result['consumption_kwh_100km']==15
