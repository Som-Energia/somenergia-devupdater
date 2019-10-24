# somenergia-devupdater


Script to deploy/update the development environment

## Setup

- Create a passwordless ssh key:
  ```bash
  ssh-keygen
  ```
- Add the new key at `~/.ssh/id_rsa.pub` it to Avatar Icon/Setting/SSH and GPG Keys in the SSH section.

- Create a directory for the repositories, for example`~/somenergia/`:

``` 
mkdir somenergia
cd somenergia/
```



If your running user is not a full sudoer,
add the following commands to `/etc/sudoers`
(provided the user is `blamer` and this file is in /home/blamer/sandbox/somenergia-devupdater

```
blamer  ALL=NOPASSWD: /usr/bin/apt
blamer  ALL=NOPASSWD: /usr/bin/dpkg
blamer  ALL=(postgres) NOPASSWD: /home/blamer/sandbox/somenergia-devupdater/pgadduser.sh
```

- Create a config.yaml file like the one in config-example.yaml
- `mkvirtualenv ci`
- `pip install yamlns consolemsg click emili`
- `./update.py`


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

