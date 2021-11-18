# RPi-based Sink Node

The Raspberry Pi-based sink node hosts the database and front ends (data query, data visualization) used in our wireless sensor network testbed.

The sink nod used in our WSN is based on a Raspberry Pi 3 model B (shortly called RPi) equipped with a 32 GB microSD card running a recent version of [Raspberry Pi OS](https://www.raspberrypi.org/software/) (previously called Raspbian).
The installation and setup of the required software components is described below.


## Contents

1. [Install MariaDB](#install-mariadb)  
2. [Install phpMyAdmin](#install-phpmyadmin)
3. [Prepare Databases](#prepare-databases)
4. [Install Grafana](#install-grafana)

### Install MariaDB

The installation of the MariaDB mainly follows the guide provided at [pimylifeup.com](https://pimylifeup.com/raspberry-pi-mysql/).
* If not done already, update your package list:  
  `sudo apt update`
* Install the MariaDB server package:  
  `sudo apt install mariadb-server`
* Secure the installation:  
  `sudo mysql_secure_installation`
    * Set the root password:  
      `[YOUR_SECURE_PASSWORD]`
* You can test the access with:  
  `sudo mysql -u root -p`


### Install phpMyAdmin

To ease the setup and configuration of the databases used, we install <a href="https://www.phpmyadmin.net/" target="_blank">`phpMyAdmin`</a> as follows:
* Install the phpMyAdmin package:  
  `sudo apt install phpmyadmin`
    * During the installation, the phpMyAdmin setup will walk you through some basic configurations:  
        * Select `Apache2` for the server
        * Choose `YES` when asked about whether to configure the database for phpmyadmin with `dbconfig-common`
        * Enter your `MySQL` password when prompted:  
          `[YOUR_SECURE_PASSWORD]`
        * Enter the password that you want to use to log into phpMyAdmin:  
          `[ANOTHER_SECURE_PASSWORD]`
* Finish Installation:  
  In MySQL 5.7 (released Oct 2015) and MySQL 8, the root MySQL user is set to authenticate using the auth_socket or caching_sha2_password plugin rather than with mysql_native_password.  
  This will prevent programs like phpMyAdmin from logging in with the root account.
    * Enable remote `mysql` access:  
      `sudo nano /etc/mysql/mariadb.conf.d/50-server.cnf`
        * Comment the line with:  
          `#bind-address=127.0.0.1`
        * Save config file (`CTRL+O` and `CTRL+X`)
    * Create a new superuser for phpMyAdmin:
        * Open up the SQL prompt from your terminal:  
          `sudo mysql -p -u root`
        * Create a new superuser (with local access only):  
          `CREATE USER 'admin'@'localhost' IDENTIFIED BY '[THIRD_SECURE_PASSWORD]';`  
          `GRANT ALL PRIVILEGES ON *.* TO 'admin'@'localhost' WITH GRANT OPTION;`  
          `FLUSH PRIVILEGES;`
    * Restart the `mysql` service:  
      `sudo /etc/init.d/mysql restart`
    * Now phpMyAdmin is available on your system.  
      You can access phpMyAdmin with the user `admin` and the previously set password.
* Additional Apache configuration:
    * Additionally, PHP should be provided:  
      `sudo apt install php php-mcrypt php-mysql`
    * Apache is running as user *www-data*, so make this user the owner of the `html` directory:  
      `sudo chown -R www-data:www-data /var/www/html`
    * Add user *pi* to this group:  
      `sudo usermod -a -G www-data pi`
    * Change html directory rights to enable write access for user `pi`:  
      `sudo chmod 775 /var/www/html/`


### Prepare Databases

For the WSN testbed, we will create an own user for the database access.

* Start MySQL:  
  `sudo mysql -u root -p`
  * Enter previously set password
* Create an own user for the WSN testbed:  
  `CREATE USER 'mywsn' IDENTIFIED BY '[FOURTH_SECURE_PASSWORD]';`
* Set the respective access rights:  
  ``GRANT ALL ON `wsn_testbed`.* TO 'mywsn'@'%';``  
  `FLUSH PRIVILEGES;`
* Exit MySQL:  
  `quit`

Further configuration and setup of the databases can now be done via `PHPmyAdmin`.


### Install Grafana

We use [Grafana](https://grafana.com/) to visualize our sensor data stored in the database.
For a download link and detailed setup instructions see [here](https://grafana.com/grafana/download).
Instructions and information on how to run the service are provided [here](https://grafana.com/docs/grafana/latest/installation/debian/#2-start-the-server).

* Install Grafana
    * Install the prerequisites needed for `Grafana` (both should be already available):  
      `sudo apt install -y adduser libfontconfig1`
    * Download the open-source edition of Grafana for Debian-based systems:  
      `wget https://dl.grafana.com/oss/release/grafana-rpi_7.1.1_armhf.deb`
    * Now install the Grafana package:  
      `sudo apt install ./grafana-rpi_7.1.1_armhf.deb`
* Start Grafana with `systemd`:
    * Start the service and verify that the service has started:  
      `sudo systemctl daemon-reload`  
      `sudo systemctl start grafana-server`  
      `sudo systemctl status grafana-server`
    * Configure the Grafana server to start at boot:  
      `sudo systemctl enable grafana-server.service`
    * Alternatively, you can do the same with `init.d`:
        * Start the service and verify that the service has started:  
          `sudo service grafana-server start`  
          `sudo service grafana-server status`
        * Configure the Grafana server to start at boot:  
          `sudo update-rc.d grafana-server defaults`
* Log in for the first time:
    * Per default, `Grafana` runs on port 3000.
    * On the first login, use `admin` for the username and password.
    * Change the admin password to `[FIFTH_SECURE_PASSWORD]`.


## Contributors

* **Dominik Widhalm** - [***DC-RES***](https://informatics.tuwien.ac.at/doctoral/resilient-embedded-systems/) - [*UAS Technikum Wien*](https://embsys.technikum-wien.at/staff/widhalm/)

Contributions of any kind to improve the project are highly welcome.
For coding bugs or minor improvements simply use pull requests.
However, for major changes or general discussions please contact [Dominik Widhalm](mailto:widhalm@technikum-wien.at?subject=RPi_SK%20on%20GitHub).


## Changelog

A list of prior versions and changes between the updates can be found inn the [CHANGELOG.md](CHANGELOG.md) file.


## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details.


## Links

In the following links for further or complementary information are listed.

#### Database

MariaDB (formerly MySQL):

- [PimpMyLifeUp](https://pimylifeup.com/raspberry-pi-mysql/)
- [ComputingForGeeks](https://computingforgeeks.com/how-to-install-mariadb-on-debian/)

InfluxData (alternatively):
- [Influxdata](https://www.influxdata.com/)


#### Visualization

- [Grafana](https://grafana.com/)
