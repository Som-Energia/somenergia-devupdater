# somenergia-devupdater


Script to deploy/update the development environment

## Setup

Some of the performed actions require sudo, if you want to make the script run unattended,
you should at least make the executing user sudoer for specific commands in `/etc/sudoers`
(provided the user is `blamer` and this file is in /home/blamer/sandbox/somenergia-devupdater):

```
blamer  ALL=NOPASSWD: /usr/bin/apt
blamer  ALL=NOPASSWD: /usr/bin/dpkg
blamer  ALL=(postgres) NOPASSWD: /home/blamer/sandbox/somenergia-devupdater/pgadduser.sh
```

- Create a passwordless ssh key:
  ```bash
  ssh-keygen
  ssh-copy-id somdevel@sf5.somenergia.coop
  ```
- Add the new key at `~/.ssh/id_rsa.pub` it to GitHub Avatar Icon/Setting/SSH and GPG Keys in the SSH section.
- Add the new key at `~/.ssh/id_rsa.pub` it to GitLab Avatar Icon/Setting/SSH and GPG Keys in the SSH section.
- Do a ssh to anyuser@github.com, just accept the remote server key as valid and close
- Do a ssh to anyuser@192.168.35.249 (gitlab), just accept the remote server key as valid and close


``` bash
sudo apt install virtualenvwrapper git
bash # to load virtualenvwrapper
mkvirtualenv -p $(which python2) erp
pip install yamlns consolemsg pathlib2 click emili

WORKINGDIR=~/somenergia
mkdir $WORKINGDIR
cd $WORKINGDIR
git clone git@github.com:Som-Energia/somenergia-devupdater.git
cd somenergia-devupdater/
```
- copy config-example.yaml as config.yaml and change email, workingpath, dbname and dbuser.

Once configured just run, and wait... waiit.....

```bash
./update.py
```

## Initial scenario


- Deploy stage
	- Install all missing apt packages (ubuntuDependencies)
	- Install wkhtmltox apt
	- Install all missing pip packages (pipDependencies)
	- Clone all missing git repositories (repositories)
	- Install as editable all python repositories that requires that (editablePackages)
	- Upgrade all outdated pip packages (if skipPipUpgrade)
	- Run `linkadons.sh`
	- firstTimeSetup substage
		- just if erp.conf does not exist
		- create the log dir
		- generate `erpserver` launcher
		- generate `erp.conf`
		- setup db users calling `pgadduser.sh`
	- Download last db backup
	- Remove existing db
	- Restore last db backup
	- Patch db for development (non-production flag, all emails set to a safe one...)
- Update the erp
- Run the erp in background while
	- pass all test commands in `repositories`





## Use cases

- First run in a computer
    - Configure postgres
    - Install apts
    - Check out repositories
- Repositories deleted
- Database deleted

# Modules Status


- [![Build Status](https://travis-ci.org/Som-Energia/somenergia-generationkwh.svg?branch=master)](https://travis-ci.org/Som-Energia/somenergia-generationkwh) somenergia-generationkwh
- [![Build Status](https://travis-ci.org/Som-Energia/plantmeter.svg?branch=master)](https://travis-ci.org/Som-Energia/plantmeter) plantmeter
- [![Build Status](https://travis-ci.org/Som-Energia/sermepa.svg?branch=master)](https://travis-ci.org/Som-Energia/sermepa) Sermepa
- [![Build Status](https://travis-ci.org/Som-Energia/somenergia-tomatic.svg?branch=master)](https://travis-ci.org/Som-Energia/somenergia-tomatic) Tomatic
- [![Build Status](https://travis-ci.org/Som-Energia/intercoop.svg?branch=master)](https://travis-ci.org/Som-Energia/intercoop) Intercoop
- [![Build Status](https://travis-ci.org/Som-Energia/somenergia-oomakotest.svg?branch=master)](https://travis-ci.org/Som-Energia/somenergia-oomakotest) oomakotest
- [![Build Status](https://travis-ci.org/Som-Energia/webforms.svg?branch=master)](https://travis-ci.org/Som-Energia/webforms) webforms

