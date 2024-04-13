import struct

import bluetooth
import uasyncio as asyncio
from machine import Pin
from micropython import const

import aioble
import queue

# org.bluetooth.service.environmental_sensing
_SERVICE_UUID = bluetooth.UUID("4fafc201-1fb5-459e-8fcc-c5c9c331914b")
# org.bluetooth.characteristic.temperature
_STEPPER_CHARACTERISTIC_UUID = bluetooth.UUID("0000aa21-0000-1000-8000-00805f9b34fb")
_TRIGGER_CHARACTERISTIC_UUID = bluetooth.UUID("aab85f5f-3a64-4dd0-b418-8b62b27d27fb")

# How frequently to send advertising beacons.
_ADV_INTERVAL_MS = 250_000

_STEP_PIN = const(18)
_DIR_PIN = const(5)
_TRIGGER_PIN = const(13)

# Register GATT server.
service = aioble.Service(_SERVICE_UUID)
stepper_characteristic = aioble.Characteristic(
    service, _STEPPER_CHARACTERISTIC_UUID, read=True, notify=True, write=True
)
trigger_characteristic = aioble.Characteristic(
    service, _TRIGGER_CHARACTERISTIC_UUID, read=True, write=True
)
aioble.register_services(service)

trigger_pin = Pin(_TRIGGER_PIN, Pin.IN)


async def stepper_task(q):
    while True:
        await stepper_characteristic.written()
        write_value = stepper_characteristic.read().decode("utf-8")
        print("Stepper value: " + write_value)

        stepper_values = write_value.split(" ")
        await q.put(stepper_values)

        await asyncio.sleep_ms(1000)


async def camera_trigger():
    while True:
        await trigger_characteristic.written()
        write_value = trigger_characteristic.read().decode("utf-8")
        print("Trigger value: " + write_value)
        if write_value == "c":
            trigger_pin.value(0)
            await asyncio.sleep_ms(1000)
            trigger_pin.value(1)


FULL_STEP_SEQUENCE_CLOCKWISE = [
    [0, 0, 0, 1],
    [0, 0, 1, 1],
    [0, 0, 1, 0],
    [0, 1, 1, 0],
    [0, 1, 0, 0],
    [1, 1, 0, 0],
    [1, 0, 0, 0],
    [1, 0, 0, 1]
]

FULL_STEP_SEQUENCE_COUNTERCLOCKWISE = [
    [1, 0, 0, 1],
    [1, 0, 0, 0],
    [1, 1, 0, 0],
    [0, 1, 0, 0],
    [0, 1, 1, 0],
    [0, 0, 1, 0],
    [0, 0, 1, 1],
    [0, 0, 0, 1]
]

STEP_DELAY_MS = 5


async def stepper_control(q):
    is_on = False
    is_clockwise = False
    speed = STEP_DELAY_MS
    step_pin = Pin(_STEP_PIN, Pin.OUT)
    dir_pin = Pin(_DIR_PIN, Pin.OUT)
    while True:
        if not q.empty():
            stepper_values = await q.get()
            is_on = bool(int(stepper_values[0]))
            is_clockwise = bool(int(stepper_values[1]))
            speed = int(stepper_values[2])
        if is_on:
            # Turn on the stepper motor
            step_sequence = FULL_STEP_SEQUENCE_CLOCKWISE if is_clockwise else FULL_STEP_SEQUENCE_COUNTERCLOCKWISE
            for sequence in step_sequence:
                for pin, state in zip([step_pin, dir_pin], sequence):
                    pin.value(state)
                await asyncio.sleep_ms(speed)
        else:
            # Turn off the stepper motor
            step_pin.off()
            dir_pin.off()
        await asyncio.sleep_ms(50)


# Serially wait for connections. Don't advertise while a central is
# connected.
async def peripheral_task():
    while True:
        async with await aioble.advertise(
                _ADV_INTERVAL_MS,
                name="ESP32",
                services=[_SERVICE_UUID],
        ) as connection:
            print("Connection from", connection.device)
            await connection.disconnected(timeout_ms=None)


# Run both tasks.
async def main():
    q = queue.Queue()
    t1 = asyncio.create_task(stepper_task(q))
    t2 = asyncio.create_task(peripheral_task())
    t3 = asyncio.create_task(stepper_control(q))
    t4 = asyncio.create_task(camera_trigger())
    await asyncio.gather(t1, t2, t3, t4)


asyncio.run(main())
