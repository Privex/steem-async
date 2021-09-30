# Benchmark Comparison Tools

This folder contains small scripts which benchmark `steem-async` as well as alternative steem/hive libraries, using simple
benchmark tasks, such as loading 1000 blocks, reading account information, etc.

This README contains results of some/all of the benchmarks that were ran on Someguy123's iMac Pro, using Python 3.9
and his home internet connection.

## Results

### Loading 1000 blocks with `beem`

```sh
chris | ~/steem-async/benchmarks $ ./bench_beem.py

[2021-09-30 06:01:27.600455] Loading last 1000 blocks using beem ...

[2021-09-30 06:03:36.533510] Total blocks: 1001

Start Time: 1632981687.6005 seconds
End Time: 1632981816.5335 seconds

Total Time: 128.9330 seconds
```

### Loading 1000 blocks with `steem-async`

```sh
chris | ~/steem-async/benchmarks $ ./bench_async.py

[2021-09-30 06:07:52.741749] Loading last 1000 blocks using steem-async ... 

[2021-09-30 06:08:10.053123] Total blocks: 1000 

Start Time: 1632982072.7419 seconds
End Time: 1632982090.0531 seconds

Total Time: 17.3112 seconds
```

## How to run the benchmarks

### Option 1. - Use the benchmarks via the PyPi package

This is the easiest method, as it doesn't require cloning the repo or setting up a virtualenv.

Simply install the package `steem-async[bench]` using pip - which will install the steem-async library,
with the `bench` extra requirements - which are the optional extra packages you need, to be able to run
all of the benchmarks.

```sh
python3.9 -m pip install -U 'steem-async[bench]'
# Alternatively - if you can't use pip via python3.x -m pip, then you can use 'pip3' instead.
pip3 install -U 'steem-async[bench]'
```

Now you should be able to call the benchmarks via the full module path:

```sh
# Run the steem-async 1000 block benchmark
python3.9 -m privex.steem.benchmarks.bench_async
# Run the beem 1000 block benchmark
python3.9 -m privex.steem.benchmarks.bench_beem
```

### Option 2. - Clone the repo and setup a dev environment

First, clone the repo:

```sh
git clone https://github.com/Privex/steem-async.git
cd steem-async
```

Now install the dependencies + create a virtualenv using `pipenv` :

```sh
# If you don't already have pipenv installed - then you'll need to install it using pip
python3.9 -m pip install -U pipenv

# Install the main deps + create the virtualenv
pipenv install

# Now install the development deps, which should include the dependencies for running the benchmark
pipenv install --dev
```

Finally, enter the virtualenv using `pipenv shell` , and run the benchmarks using either `python3.x -m` ,
or cd into the folder and execute them `./bench_async.py`

```sh
# Activate the virtualenv
pipenv shell

###
# Run the benchmarks using python's module runner:
###

# Run the steem-async 1000 block benchmark
python3 -m benchmarks.bench_async
# Run the beem 1000 block benchmark
python3 -m benchmarks.bench_beem

###
# Alternatively, you can run the benchmarks as individual files
###
cd benchmarks
# Run the steem-async 1000 block benchmark
./bench_async.py
# Run the beem 1000 block benchmark
./bench_beem.py
```


