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
- Add the new key at `~/.ssh/id_rsa.pub` it to Avatar Icon/Setting/SSH and GPG Keys in the SSH section.

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

