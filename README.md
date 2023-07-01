# ds18b20
rpi code to read ds18b20 sensor(s) and save info to .csv and/or upload to other backends

It’s inteded to run on a raspberry pi
You can connect several ds18b20 sensors in parallel and it will read all of them.
## Setup
The details on how to make the sensors work on rpi can be found with google but the **nano** version is
* connect sensor plus to rpi 3.3v, ground to rpi ground and sensor data to rpi #4.
* activate 1-wire protocol
 * run "sudo raspi-config" then select "3 interface options" -> "I7 1-wire" -> enable
* load 1wire modules
 * echo w1-gpio |sudo tee -a /etc/modules-load.d/modules.conf
 * echo w1-therm |sudo tee -a /etc/modules-load.d/modules.conf
* activate it
 * sudo reboot

with some luck you can now see the temperature sensors with
`ls -l /sys/bus/w1/devices/`
or to see the temperature: `grep -s . /sys/bus/w1/devices/*/temperature`
Note that the temperature shown need to be divided with 1000 to get it in Celsius.


## Program
The program is designed to read all sensors found and save the data do multiple destinations.
Some help can be received weith `./load_temp.py --help`
If the program is started without any config file or parameters a default config file is created as log_temp.ini.

The .ini file contains config information for the different way to save the temp. By default all are disabled ("enabled=false").
Each section contains what's required for that to destination to work. Things like username, password, hostname, database and so on. 
The sections are config, sensors, mqtt, db and influx.
### config
- max\_log\_time: The longest time between logs, default=60
- max\_list\_length: To detect faster temperature changes it keep a list of the last few measurements and look for diff between lowest and highest number. The default length of that list is 10
- min\_time\_between\_reads: minimum seconds between reads. Note that if it is several sensors it may take longer than this but it will never read faster. Default = 10
- min\_temp\_diff: It will look at the diff between lowest and highest temp in the list and if the diff is more than this it is logged. Default=0.5

### sensors
You may want to have some kind of more descriptive label than the sensor serial number. Here you define the label you want for each serial number.

### mqtt/db/influx
Info on how to connect to the different destinations. For details see the example config file or source code.
