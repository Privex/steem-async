# Steem Async
### Async Steem library - A simple Python library for asynchronous interactions with Steem RPC nodes (and forks)

**Official Repo:** https://github.com/privex/steem-async

### Quick Install / Usage

**WARNING:** Due to use of modern Python features such as dataclasses, you MUST use **Python 3.7** or newer. This
library is **not compatible with Python 3.6 or older versions**.


```sh
pip3 install steem-async
```

```python
import asyncio
from privex.steem import SteemAsync


async def main():
    # All init params are optional, but are included to make you aware of them :)
    s = SteemAsync(rpc_nodes=['https://steemd.privex.io'], max_retry=4, retry_delay=3)
    # If using a fork based on older Steem, disable appbase to use the classic ``call`` JsonRPC method
    s.config_set('use_appbase', False)
    # If needed, you can customise the headers used
    s.config_set('headers', {'content-type': 'application/json'})
       
    ### 
    # Get accounts
    ###
    accounts = await s.get_accounts('someguy123', 'privex')
    print(accounts['someguy123'].balances)
    # {'STEEM': <Amount '16759.930 STEEM' precision=3>, 'SBD': <Amount '78.068 SBD' precision=3>,
    # 'VESTS': <Amount '277045077.603020 VESTS' precision=6>}
    
    print(accounts['privex'].created)
    # '2017-02-04T18:07:21'
    
    ###
    # Bulk load a range of blocks (uses batch calling, request chunking, and auto retry)
    ###    
    blocks = await s.get_blocks(10000, 20000)
    print(blocks[100].number)
    # 10100
    
    ###  
    # If there isn't a wrapper function for what you need, you can use json_call and api_call directly:
    ###
    
    # Appbase call
    res = await s.json_call('condenser_api.get_block', [123])
    block = res['result']
    print(block['witness'])
    # 'someguy123'
    
    # Non-appbase call
    block = await s.api_call('database_api', 'get_block', [123])
    print(block['witness'])
    # 'someguy123'

asyncio.run(main())

```


For full parameter documentation, IDEs such as PyCharm and even Visual Studio Code should show our PyDoc
comments when you try to use the class.

For PyCharm, press F1 with your keyboard cursor over the class to see full function documentation, including
return types, parameters, and general usage information. You can also press CMD-P with your cursor inside of 
a method's brackets (including the constructor brackets) to see the parameters you can use.

Alternatively, just view the files inside of `privex/steem/` - most methods and constructors
are adequently commented with PyDoc.


# Information

This Async Steem library has been developed at [Privex Inc.](https://www.privex.io) by @someguy123 to allow for
asynchronous interactions with a Steem RPC node (and forks such as GOLOS) 

It uses the [httpx library](https://www.encode.io/httpx/async/) library instead of `requests` to enable
full async support.


    +===================================================+
    |                 © 2019 Privex Inc.                |
    |               https://www.privex.io               |
    +===================================================+
    |                                                   |
    |        Python Async Steem library                 |
    |        License: X11/MIT                           |
    |                                                   |
    |        Core Developer(s):                         |
    |                                                   |
    |          (+)  Chris (@someguy123) [Privex]        |
    |                                                   |
    +===================================================+
    
    Async Steem library - A simple Python library for asynchronous interactions with Steem RPC nodes (and forks)
    Copyright (c) 2019    Privex Inc. ( https://www.privex.io )


# Install

**WARNING:** Due to use of modern Python features such as dataclasses, you MUST use **Python 3.7** or newer. This
library is **not compatible with Python 3.6 or older versions**.

### Install from PyPi using `pip`

You can install this package via pip:

```sh
pip3 install steem-async
```

### (Alternative) Manual install from Git

If you don't want to PyPi (e.g. for development versions not on PyPi yet), you can install the 
project directly from our Git repo.

Unless you have a specific reason to manually install it, you **should install it using pip3 normally**
as shown above.

**Option 1 - Use pip to install straight from Github**

```sh
pip3 install git+https://github.com/Privex/steem-async
```

**Option 2 - Clone and install manually**

```bash
# Clone the repository from Github
git clone https://github.com/Privex/steem-async
cd steem-async

# RECOMMENDED MANUAL INSTALL METHOD
# Use pip to install the source code
pip3 install .

# ALTERNATIVE INSTALL METHOD
# If you don't have pip, or have issues with installing using it, then you can use setuptools instead.
python3 setup.py install
```


# Logging

By default, this package will log anything >=WARNING to the console. You can override this by adjusting the
`privex.steem` logger instance. 

We recommend checking out our Python package [Python Loghelper](https://github.com/Privex/python-loghelper) which
makes it easy to manage your logging configuration, and copy it to other logging instances such as this one.

```python
# Without LogHelper
import logging
l = logging.getLogger('privex.steem')
l.setLevel(logging.ERROR)

# With LogHelper (pip3 install privex-loghelper)
from privex.loghelper import LogHelper
# Set up logging for **your entire app**. In this case, log only messages >=error
lh = LogHelper('myapp', handler_level=logging.ERROR)
lh.add_file_handler('test.log')      # Log messages to the file `test.log` in the current directory
lh.copy_logger('privex.steem')       # Easily copy your logging settings to any other module loggers
log = lh.get_logger()                # Grab your app's logging instance, or use logging.getLogger('myapp')
log.error('Hello World')
```

# Contributing

We're very happy to accept pull requests, and work on any issues reported to us. 

Here's some important information:

**Reporting Issues:**

 - For bug reports, you should include the following information:
     - Version of `privex-steem` and `httpx` tested on - use `pip3 freeze`
        - If not installed via a PyPi release, git revision number that the issue was tested on - `git log -n1`
     - Your python3 version - `python3 -V`
     - Your operating system and OS version (e.g. Ubuntu 18.04, Debian 7)
 - For feature requests / changes
     - Please avoid suggestions that require new dependencies. This tool is designed to be lightweight, not filled with
       external dependencies.
     - Clearly explain the feature/change that you would like to be added
     - Explain why the feature/change would be useful to us, or other users of the tool
     - Be aware that features/changes that are complicated to add, or we simply find un-necessary for our use of the tool may not be added (but we may accept PRs)
    
**Pull Requests:**

 - We'll happily accept PRs that only add code comments or README changes
 - Use 4 spaces, not tabs when contributing to the code
 - You can use features from Python 3.4+ (we run Python 3.7+ for our projects)
    - Features that require a Python version that has not yet been released for the latest stable release
      of Ubuntu Server LTS (at this time, Ubuntu 18.04 Bionic) will not be accepted. 
 - Clearly explain the purpose of your pull request in the title and description
     - What changes have you made?
     - Why have you made these changes?
 - Please make sure that code contributions are appropriately commented - we won't accept changes that involve uncommented, highly terse one-liners.

**Legal Disclaimer for Contributions**

Nobody wants to read a long document filled with legal text, so we've summed up the important parts here.

If you contribute content that you've created/own to projects that are created/owned by Privex, such as code or documentation, then you might automatically grant us unrestricted usage of your content, regardless of the open source license that applies to our project.

If you don't want to grant us unlimited usage of your content, you should make sure to place your content
in a separate file, making sure that the license of your content is clearly displayed at the start of the file (e.g. code comments), or inside of it's containing folder (e.g. a file named LICENSE). 

You should let us know in your pull request or issue that you've included files which are licensed
separately, so that we can make sure there's no license conflicts that might stop us being able
to accept your contribution.

If you'd rather read the whole legal text, it should be included as `privex_contribution_agreement.txt`.

# License

This project is licensed under the **X11 / MIT** license. See the file **LICENSE** for full details.

Here's the important bits:

 - You must include/display the license & copyright notice (`LICENSE`) if you modify/distribute/copy
   some or all of this project.
 - You can't use our name to promote / endorse your product without asking us for permission.
   You can however, state that your product uses some/all of this project.



# Thanks for reading!

**If this project has helped you, consider [grabbing a VPS or Dedicated Server from Privex](https://www.privex.io) - prices start at as little as US$8/mo (we take cryptocurrency!)**