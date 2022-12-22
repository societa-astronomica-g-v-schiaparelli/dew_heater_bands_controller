#!/usr/bin/env python3.11

# DEW HEATER (https://github.com/societa-astronomica-g-v-schiaparelli/dew_heater_bands_controller)
# Copyright (c) 2021-2022 Società Astronomica G.V. Schiaparelli
# Paolo Galli <paolo.galli@astrogeo.va.it>


import asyncio
import logging
import os
from copy import deepcopy
from datetime import datetime, timedelta

import numpy as np
import skyfield.almanac
import skyfield.api
import ujson
import uvloop
from aiohttp import ClientSession, ClientTimeout, web
from aiohttp_sse import sse_response
from gpiozero import DigitalOutputDevice


#####################################################################
# BASIC CONFIGURATION


logging_format = "[%(asctime)s] (%(levelname)s) %(module)s - %(funcName)s: %(message)s"
logging.basicConfig(level=logging.DEBUG, format=logging_format)

class ColoredFormatter(logging.Formatter):
    """ Colored formatter for the logging package. """

    def __init__(self, fmt=None, datefmt=None, style='%', validate=True, *, defaults=None):
        super().__init__(fmt, datefmt, style, validate, defaults=defaults)
        colors = {
            "red": "\x1b[31;20m", "bold_red": "\x1b[31;1m",
            "green": "\x1b[32;20m", "bold_green": "\x1b[32;1m",
            "yellow": "\x1b[33;20m", "bold_yellow": "\x1b[33;1m",
            "blue": "\x1b[34;20m", "bold_blue": "\x1b[34;1m",
            "grey": "\x1b[37;20m", "bold_grey": "\x1b[37;1m",
            "reset": "\x1b[0m"
        }
        self._default_formatter = logging.Formatter(fmt)
        self._formatters = {
            100: logging.Formatter(colors["bold_blue"] + fmt + colors["reset"]),
            logging.DEBUG: logging.Formatter(colors["grey"] + fmt + colors["reset"]),
            logging.INFO: logging.Formatter(colors["green"] + fmt + colors["reset"]),
            logging.WARNING: logging.Formatter(colors["yellow"] + fmt + colors["reset"]),
            logging.ERROR: logging.Formatter(colors["red"] + fmt + colors["reset"]),
            logging.CRITICAL: logging.Formatter(colors["bold_red"] + fmt + colors["reset"])
        }

    def format(self, record):
        return self._formatters.get(record.levelno, self._default_formatter).format(record)

(logger := logging.getLogger(__name__)).setLevel(logging.DEBUG)
logger.propagate = False
(logger_handler := logging.StreamHandler()).setFormatter(ColoredFormatter(fmt=logging_format))
logger.addHandler(logger_handler)

SCRIPT_PATH = os.path.abspath(os.path.dirname(__file__))

relays = {
    "main":  DigitalOutputDevice(pin="GPIO2", active_high=False),
    "guide": DigitalOutputDevice(pin="GPIO3", active_high=False)
}


#####################################################################
# UPDATER


class DewHeaterHandler():
    """ Dew heater updater class, with utility functions to handle. """

    _updater_lock = asyncio.Lock()

    def __init__(self, relays: dict[str, DigitalOutputDevice], site_latitude: float,
                 site_longitude: float, site_elevation: float, auto_update: bool = True,
                 temp_threshold: float = 4, time_threshold: int = 1800) -> None:
        self._status = {"auto": auto_update}
        self._relays = relays
        self._update_relay_status()
        # setup location for Sun altitude
        self._ts_skyfield = skyfield.api.load.timescale()
        self._site = skyfield.api.wgs84.latlon(site_latitude, site_longitude, site_elevation)
        self._sun_is_up = skyfield.almanac.sunrise_sunset(skyfield.api.load("de421.bsp"), self._site)
        # setup threshold
        self._temp_threshold = temp_threshold
        self._time_threshold = time_threshold
        self._time = datetime.utcnow() - timedelta(seconds=self._time_threshold+1)

    @property
    def status(self) -> dict:
        return self._status

    @property
    def auto_update(self) -> bool:
        return self.status["auto"]

    @auto_update.setter
    def auto_update(self, value: bool) -> None:
        self._status["auto"] = value

    @property
    def relays(self) -> dict[str, DigitalOutputDevice]:
        return self._relays

    def _update_relay_status(self) -> None:
        self._status.update({"telescope": {telescope: relay.is_active for telescope, relay in self.relays.items()}})

    def relay_on(self, relay: str) -> None:
        if not self.relays[relay].is_active:
            self.relays[relay].on()
            self._update_relay_status()

    def relay_off(self, relay: str) -> None:
        if self.relays[relay].is_active:
            self.relays[relay].off()
            self._update_relay_status()

    async def _get_meteo_data(self) -> tuple[float]:
        """ Function to get temperature and humidity at the telescope location. """
        async with ClientSession(timeout=ClientTimeout(total=5)) as session:
            async with session.get("https://astrogeo.va.it/data/stazioni/cdf.json") as resp:
                meteo_data = await resp.json(loads=ujson.loads)
        return float(meteo_data["tempcorr"]), float(meteo_data["rhcorr"])

    async def update_status(self) -> None:
        if self.auto_update:
            async with self._updater_lock:
                if self._sun_is_up(self._ts_skyfield.now()):
                    logger.info("System disabled (daily hours)")
                    for telescope in self.relays:
                        self.relay_off(telescope)
                else:
                    logger.info("Starting auto update routine")
                    try:
                        temperature, humidity = await self._get_meteo_data()
                        # compute dewpoint
                        a, m, Tn = 6.116441, 7.591386, 240.7263
                        Pws = a * 10**(m * temperature / (temperature + Tn))
                        Pw = Pws * humidity / 100
                        dew_point = round(Tn / ((m / np.log10(Pw / a)) - 1), 1)
                    except Exception as e:
                        logger.exception(e)
                        logger.info("System disabled (error retriving parameters)")
                        for telescope in self.relays:
                            self.relay_off(telescope)
                    else:
                        logger.info(f"Temperature: {temperature} °C, Dew Point: {dew_point} °C")
                        delta = temperature - dew_point
                        if delta < self._temp_threshold:
                            logger.info("System enabled")
                            self._time = datetime.utcnow()
                            for telescope in self.relays:
                                self.relay_on(telescope)
                        elif delta > self._temp_threshold and (datetime.utcnow() - self._time).seconds > self._time_threshold:
                            logger.info("System disabled")
                            for telescope in self.relays:
                                self.relay_off(telescope)
                        else:
                            logger.info("Waiting for disabling system")

updater = DewHeaterHandler(relays, 45.86833333, 8.77055556, 1226)


#####################################################################
# WEBSERVER


routes = web.RouteTableDef()

@routes.get("/")
async def webserver_route_root(request: web.Request):
    return web.FileResponse(f"{SCRIPT_PATH}/html/index.html")

@routes.get("/static/{file}")
async def webserver_route_static(request: web.Request):
    return web.FileResponse(f"{SCRIPT_PATH}/html/{request.match_info['file']}")

@routes.get("/api")
async def webserver_route_api(request: web.Request):
    params = request.rel_url.query
    headers = {"Access-Control-Allow-Origin": "*"}
    # check "json" param
    if "json" in params:
        # try parse and check syntax
        try:
            data = ujson.loads(params["json"])
            assert "cmd" in data
            assert data["cmd"] in ("set", "status")
            if data["cmd"] == "set":
                assert "params" in data and data["params"]
                assert set(data["params"]) <= {"auto", "telescope"}
                if "auto" in data["params"]:
                    assert isinstance(data["params"]["auto"], bool)
                if "telescope" in data["params"]:
                    assert set(data["params"]["telescope"]) <= set(updater.relays)
                    for telescope in data["params"]["telescope"]:
                        assert isinstance(data["params"]["telescope"][telescope], bool)
            elif data["cmd"] == "status":
                assert "params" not in data
        except Exception:
            return web.json_response({"rsp": "Error: wrong json format"}, status=400, headers=headers, dumps=ujson.dumps)
        # set
        if data["cmd"] == "set":
            if "auto" in data["params"]:
                updater.auto_update = data["params"]["auto"]
                logger.info(f"Auto update {'enabled' if updater.auto_update else 'disabled'}")
                await updater.update_status()
            if "telescope" in data["params"]:
                if updater.auto_update:
                    logger.error("Controller in automatic mode, enable manual mode first")
                    return web.json_response({"rsp": "Error: controller in automatic mode, enable manual mode first"}, headers=headers, dumps=ujson.dumps)
                for telescope in updater.relays:
                    if telescope in data["params"]["telescope"]:
                        logger.info(f"{telescope.capitalize()} {'enabled' if data['params']['telescope'][telescope] else 'disabled'}")
                        (updater.relay_on if data["params"]["telescope"][telescope] else updater.relay_off)(telescope)
            return web.json_response({"rsp": "done"}, headers=headers, dumps=ujson.dumps)
        # status
        elif data["cmd"] == "status":
            return web.json_response({"rsp": updater.status}, headers=headers, dumps=ujson.dumps)
        # command error
        else:
            return web.json_response({"rsp": "Error: unknown request"}, status=400, headers=headers, dumps=ujson.dumps)
    # param error
    else:
        return web.json_response({"rsp": "Error: unknown params"}, status=400, headers=headers, dumps=ujson.dumps)

@routes.get("/status-sse")
async def webserver_route_status_sse(request: web.Request):
    async with sse_response(request) as resp:
        last_status = {}
        while True:
            if updater.status != last_status:
                await resp.send(ujson.dumps(updater.status))
                last_status = deepcopy(updater.status)
            await asyncio.sleep(0.1)
    return resp


#####################################################################
# MAIN


async def main():

    # WEBSERVER

    # setup application
    webserver = web.Application()
    webserver.add_routes(routes)

    # setup runner and start site
    runner = web.AppRunner(webserver)
    await runner.setup()
    site = web.TCPSite(runner, port=8001)
    await site.start()

    logger.info("Webserver started!")

    # UPDATER

    logger.info("Updater started!")
    while True:
        await updater.update_status()
        await asyncio.sleep(180)


try:
    logger.log(100, "[MAIN] Starting app: dew_heater")
    uvloop.install()
    asyncio.run(main())
except (KeyboardInterrupt, SystemExit):
    logger.log(100, "[MAIN] Interrupt detected, exit")
