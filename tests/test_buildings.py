import pytest
from datetime import datetime


@pytest.mark.anyio
async def test_create_read_sensor_update_delete_sensor(client):
    building_id = "sensor_bldg_1"

    # Crear edificio para el sensor
    await client.post("/buildings/", json={
        "id": building_id,
        "name": "Sensor Test Building",
        "address": "123 Sensor St"
    })

    sensor_data = {
        "id": "sensor001",
        "name": "Temp Sensor 1",
        "type": "temperature",
        "building_id": building_id,
        "floor": 1,
        "room": 101
    }

    # Crear sensor
    response = await client.post("/sensors/", json=sensor_data)
    assert response.status_code == 200
    assert response.json()["message"] == "Sensor created successfully"

    # Leer sensor
    response = await client.get(f"/sensors/{sensor_data['id']}")
    assert response.status_code == 200
    sensor = response.json()
    assert sensor["type"] == "temperature"

    # Actualizar sensor
    updated_data = sensor_data.copy()
    updated_data["name"] = "Updated Temp Sensor"
    response = await client.put(f"/sensors/{sensor_data['id']}", json=updated_data)
    assert response.status_code == 200
    assert response.json()["message"] == "Sensor updated successfully"

    # Verificar actualización
    response = await client.get(f"/sensors/{sensor_data['id']}")
    assert response.status_code == 200
    assert response.json()["name"] == "Updated Temp Sensor"

    # Eliminar sensor
    response = await client.delete(f"/sensors/{sensor_data['id']}")
    assert response.status_code == 200
    assert response.json()["message"] == "Sensor deleted successfully"

    # Intentar leer sensor eliminado
    response = await client.get(f"/sensors/{sensor_data['id']}")
    assert response.status_code == 404


@pytest.mark.anyio
async def test_get_sensors_list(client):
    building_id = "sensor_bldg_2"
    await client.post("/buildings/", json={
        "id": building_id,
        "name": "Sensor Building 2",
        "address": "456 Sensor Ave"
    })

    sensor1 = {
        "id": "sensor100",
        "name": "Humidity Sensor 1",
        "type": "humidity",
        "building_id": building_id,
        "floor": 2,
        "room": 201
    }

    sensor2 = {
        "id": "sensor101",
        "name": "Temperature Sensor 2",
        "type": "temperature",
        "building_id": building_id,
        "floor": 2,
        "room": 202
    }

    await client.post("/sensors/", json=sensor1)
    await client.post("/sensors/", json=sensor2)

    # Obtener sensores para un edificio específico
    response = await client.get(f"/sensors/?building_id={building_id}")
    assert response.status_code == 200
    sensors = response.json()
    assert len(sensors) >= 2
    assert any(s["id"] == "sensor100" for s in sensors)
    assert any(s["id"] == "sensor101" for s in sensors)

    # Obtener todos los sensores
    response = await client.get("/sensors/")
    assert response.status_code == 200
    all_sensors = response.json()
    assert len(all_sensors) >= 2


@pytest.mark.anyio
async def test_sensor_readings(client):
    building_id = "sensor_bldg_3"
    sensor_id = "sensor200"

    # Crear edificio
    await client.post("/buildings/", json={
        "id": building_id,
        "name": "Building with readings",
        "address": "789 Reading Rd"
    })

    # Crear sensor
    sensor = {
        "id": sensor_id,
        "name": "Temperature Sensor",
        "type": "temperature",
        "building_id": building_id,
        "floor": 3,
        "room": 301
    }
    await client.post("/sensors/", json=sensor)

    reading_payload = {
        "sensor_id": sensor_id,
        "type": "temperature",
        "temperature": 25.5
    }

    # Crear lectura de sensor
    response = await client.post(f"/sensors/{sensor_id}/value", json=reading_payload)
    assert response.status_code == 200
    assert response.json()["message"] == "Sensor reading created successfully"

    # Obtener lecturas del sensor
    response = await client.get(f"/sensors/readings/{sensor_id}")
    assert response.status_code == 200
    readings = response.json()
    assert isinstance(readings, list)
    assert len(readings) >= 1
    assert "temperature" in readings[0]
    assert readings[0]["temperature"] == 25.5

    # Intentar obtener lecturas para sensor inexistente
    response = await client.get("/sensors/readings/unknown_sensor")
    assert response.status_code == 404
