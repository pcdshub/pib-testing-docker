# Base docker files for IOCs

## Notes

### Packages removed from the standard IOC machine install

```
emacs-common
gnome-terminal
gtk2
kernel
kernel-devel
kernel-headers
mariadb
vim-X11
git (git-2.18 installed from SCL)

```


Anything X related:
```
xorg-x11-font-utils
xorg-x11-fonts-100dpi
xorg-x11-fonts-75dpi
xorg-x11-fonts-Type1
xorg-x11-fonts-misc
xorg-x11-server-utils
xorg-x11-utils
xorg-x11-xbitmaps
xorg-x11-xinit
libX11
libX11-common
libXScrnSaver
libXaw
libXcomposite
libXcursor
libXfont
libXft
libXinerama
libXmu
libXp
libXpm
libXrandr
libXrender
libXt
libXt-devel
libXtst
libXxf86vm
```

and Qt:

```
qt
qt-devel
qt-settings
qt-x11
```

General utilities:

```
nmap
nmap-ncat
```

### TODO
