# RCM-dew_heater

_Remotizzazione Cupola Mascioni - Script and webserver to control dew heater bands_

The controller is a python script meant to run on an RPi and use GPIOs to control a relay board with two outputs. The two relays are connected to two custom dew heater bands ([DIY, see here](http://www.astrodeep.com/25-come-costruire-delle-fasce-anticondensa.html), one for the main telescope and one for the guide telescope) and control their powering.

The relays can be controlled in two ways:

- **Automatic** _(default)_: bands are controlled automatically, based on the time of sunrise/sunset and on the weather conditions.

- **Manual**: bands are manually controlled by the operator through network requests or using the appropriate web page.

You can interact using:

- **Web page**, route `/`.
- **API**, route `/api`.

## Code structure

The code is completely asynchronous and consists of two parts:

- **Web server**, developed with the [aiohttp](https://pypi.org/project/aiohttp/) library, by default active on port `8001`.

- **Updater** for the management of the bands, executed every five minutes. The behavior is based both on the time of sunrise and sunset of the Sun (through the [skyfield](https://pypi.org/project/skyfield/) library) and on the weather conditions (through the usage of data from the weather station at the observatory). Thresholds are set to better manage the switches. The bands management is done with the [gpiozero](https://pypi.org/project/gpiozero/) library.

## API description

The APIs are accessible through http GET requests such as:

```
/api?json={"cmd":"command"}
```

### Changing the setting of the bands

```
/api?json={"cmd":"set","params":{"auto":value,"telescope":{"main":value,"guide":value}}}
```

Replace `value` with `true` or `false`, depending on the desired configuration. All parameters and subparameters of the `params` key are optional.

Reply:

- `done` in case of successful request;
- a message indicating the type of error encountered.

Examples:

- Deactivate automatic mode and activate both bands:

  ```
  /api?json={"cmd":"set","params":{"auto":false,"telescope":{"main":true,"guide":true}}}
  ```

  ```
  {"rsp": "done"}
  ```

  or only one band:

  ```
  /api?json={"cmd":"set","params":{"auto":false,"telescope":{"main":true}}}
  ```

  ```
  {"rsp": "done"}
  ```

- Attempt to manually activate a band while automatic mode is active:

  ```
  /api?json={"cmd":"set","params":{"telescope":{"main":true}}}
  ```

  ```
  {"rsp": "Error: controller in automatic mode"}
  ```

### Status of the bands

```
/api?json={"cmd":"status"}
```

```
{
  "rsp": {
    "auto": false | true,
    "telescope": {
      "main": false | true,
      "guide": false | true
    }
  }
}
```

## Get meteo data for the dew point value

The code uses the [dew point](https://en.wikipedia.org/wiki/Dew_point) to automatically manage the bands; however, the dew point depends on the observing site location. The controller uses the data from the weather station at our observatory, but if you want to use your own data, fill the following template and replace the original code in the `DewHeaterHandler` class.

```python
async def _get_meteo_data(self) -> tuple[float]:
    """ Function to get temperature and humidity at the telescope location. """
    # implement here your code to retrive weather parameters
    ...
    # then return temperature and humidity
    return temperature, humidity
```

## Prerequisites, installation and detail of the implementation in Mascioni dome

Tested on Raspberry Pi 4 with Ubuntu Server 20.04.

Install the following packages:

```
sudo apt install python3-venv python3-dev python3-pip
```

Create a virtual environment in the `RCM-dew_heater` folder and install the necessary packages:

```
python3 -m venv venv
source venv/bin/activate
pip3 install wheel
pip3 install -r requirements.txt
```

Service to automatically start the code (modify the paths according to what you need) to put in the path `/etc/systemd/system/dew_heater.service`:

```
[Unit]
Description=Script and webserver to control the dew heater bands

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/RCM-dew_heater
ExecStart=/home/ubuntu/RCM-dew_heater/venv/bin/python3 /home/ubuntu/RCM-dew_heater/dew_heater.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Enable with:

```
sudo systemctl enable --now dew_heater.service
```
