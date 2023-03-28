# rosetta-multipass

Would you also like to run `amd64` binaries in your [Multipass](https://multipass.run/) VMs on an M1 Mac? This is a guide/tool to enable [Rosetta](https://developer.apple.com/documentation/virtualization/running_intel_binaries_in_linux_vms_with_rosetta) without official support from Multipass. 

## Rosetta Installation (macOS host)

First you need to [install Rosetta](https://osxdaily.com/2020/12/04/how-install-rosetta-2-apple-silicon-mac/) on your host system:

```sh
softwareupdate --install-rosetta --agree-to-license
```

You should now have the `rosetta` translator binary:

```sh
% tree /Library/Apple/usr/libexec/oah
/Library/Apple/usr/libexec/oah
├── RosettaLinux
│   └── rosetta # <- this one
├── debugserver -> /usr/libexec/rosetta/debugserver
├── libRosettaRuntime
├── runtime -> /usr/libexec/rosetta/runtime
└── translate_tool -> /usr/libexec/rosetta/translate_tool
```

**Note**: If you do not get the `RosettaLinux/rosetta` binary, try following the [UTM Rosetta Guide](https://docs.getutm.app/advanced/rosetta/) first, which should install Rosetta for you.

## Rosetta Installation (Ubuntu guest)

Copy the `RosettaLinux/rosetta` binary to your guest VM. In this example the binary has been copied to `/bin/rosetta`, but any path should work. Make sure that you can run the binary from inside the VM:

```
$ /bin/rosetta
rosetta error: Rosetta is only intended to run on Apple Silicon with a macOS host using Virtualization.framework with Rosetta mode enabled
Trace/breakpoint trap (core dumped)
```

The error is expected, you can read more about it in a [Quick look at Rosetta on Linux](https://threedots.ovh/blog/2022/06/quick-look-at-rosetta-on-linux/). 

### Using `mount-rosetta.py`

To fix the error you can create a FUSE mount using `mount-rosetta.py`, which implements the `ioctl` required for the Rosetta handshake:

```sh
sudo apt install libfuse2
sudo python -m pip install fusepy
```

**Note**: To mount without root, edit `/etc/fuse.conf` and uncomment `user_allow_other`. This shouldn't be necessary unless you are developing the script.

Now you can run the script:

```sh
sudo python mount-rosetta.py /bin/rosetta
```

This will shadow the `/bin/rosetta` binary and handle the necessary `ioctl` calls. To confirm you you can run:

```sh
$ /bin/rosetta
Usage: rosetta <x86_64 ELF to run>

Optional environment variables:
ROSETTA_DEBUGSERVER_PORT    wait for a debugger connection on given port

version: Rosetta-289.7
```

**Note**: You will have to run `mount-rosetta.py` in the background.

### Installing the binfmt handler (guest)

To register `rosetta` for `amd64` binaries:

```
sudo apt install binfmt-support
sudo update-binfmts --install rosetta /bin/rosetta \
    --magic "\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x3e\x00" \
    --mask "\xff\xff\xff\xff\xff\xfe\xfe\x00\xff\xff\xff\xff\xff\xff\xff\xff\xfe\xff\xff\xff" \
    --credentials yes --preserve no --fix-binary no
```

**Important**: If you want to use `--fix-binary yes` you will have to run `mount-rosetta.py` before the `update-binfmts` command.

### Running an `amd64` executable

You should now be able to execute a statically linked executable:

```sh
$ ./tests/main-static
Hello from Rosetta!
```

### Creating a service

You can create `/etc/systemd/system/rosetta.service`:

```
[Unit]
Description=Rosetta Mount Service

[Service]
ExecStart=/usr/bin/python3 /home/ubuntu/.local/bin/mount-rosetta.py /bin/rosetta
Environment=PYTHONUNBUFFERED=1
Restart=on-failure

[Install]
WantedBy=default.target
```

See [here](https://github.com/torfsen/python-systemd-tutorial) for more information.

```
sudo systemctl list-unit-files | grep rosetta
sudo systemctl enable rosetta.service
sudo systemctl start rosetta.service
```

## Installing shared libraries (experimental)

**Warning**: This section is super experimental and unlikely to yield great results. That being said, it is possible to run clang compiled for `amd64` and build something.

Running a dynamically linked binary will not work properly at this point:

```
$ ./tests/main-dynamic
./tests/main-dynamic: error while loading shared libraries: libc.so.6: cannot open shared object file: No such file or directory
```

To fix this (only tested on Ubuntu 22.04) you can run the following commands:

```
sudo apt install g++-multilib-x86-64-linux-gnu gcc-multilib-x86-64-linux-gnu
sudo ln -s /usr/x86_64-linux-gnu/lib64 /lib64
export LD_LIBRARY_PATH=/usr/x86_64-linux-gnu/lib
```

At this point things are working:

```
./tests/main-dynamic
Hello from Rosetta!
```

**Note**: For other distributions you can search for `multilib` or `multiarch` packages or look for guides on getting qemu usermode emulation to work.

### Fixing some dynamic linker errors

Since `/usr/x86_64-linux-gnu` is meant for compiling things and not running you might have to replace some `.so` files that are actually linker scripts with the binaries:

```
$ sudo -i
$ cd /usr/x86_64-linux-gnu/lib
$ rg GROUP # lists fake files
libc.so
5:GROUP ( /usr/x86_64-linux-gnu/lib/libc.so.6 /usr/x86_64-linux-gnu/lib/libc_nonshared.a  AS_NEEDED ( /usr/x86_64-linux-gnu/lib64/ld-linux-x86-64.so.2 ) )
libm.so
4:GROUP ( /usr/x86_64-linux-gnu/lib/libm.so.6  AS_NEEDED ( /usr/x86_64-linux-gnu/lib/libmvec.so.1 ) )

$ mv libc.so libc.so.script
$ cp libc.so.6 libc.so
$ mv libm.so libm.so.script
$ cp libm.so.6 libm.so
```

### Cross-compiling libraries

If you need to install something like [zlib](https://zlib.net) for `amd64` you can use [Zig](https://zig.news/kristoff/cross-compile-a-c-c-project-with-zig-3599) for easy cross compiling:

```
sudo snap install zig --classic --edge
git clone https://github.com/madler/zlib
cd zlib
CC="zig cc -target x86_64-linux-musl" CXX="zig c++ -target x86_64-linux-musl" AR="zig ar" RANLIB="zig ranlib" uname_S="Linux" uname_M="x86_64" C11_ATOMIC=yes USE_JEMALLOC=no USE_SYSTEMD=no ./configure --prefix /usr/x86_64-linux-gnu
make
sudo make install
```

For CMake project you can use [zig-cross](https://github.com/mrexodia/zig-cross) as a base.

### Multithreading

According to [Quick look at Rosetta on Linux](https://threedots.ovh/blog/2022/06/quick-look-at-rosetta-on-linux/) you might run into issues if the VM is not running in Total Store Ordering (TSO) mode. The solution should be to wrap `rosetta` in a `taskset` command during `update-binfmts`. This was not explored further.