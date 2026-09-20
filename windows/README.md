# HackDex Manager Windows Desktop

This directory contains the Windows desktop packaging and launcher components for HackDex Manager.

The Windows edition must preserve the existing HackDex Manager user interface.

The existing:

- HTML templates
- CSS
- JavaScript
- navigation
- cards
- dialogs
- setup flow
- light/dark modes

remain the authoritative UI.

The Windows desktop edition changes only the hosting, filesystem integration, application lifecycle, and packaging layers.

## Windows goals

- Native installed Windows application
- No Docker requirement
- No browser URL required
- No separate Python installation
- Existing HackDex Manager UI hosted inside a desktop window
- Local folders supported
- Mapped drives supported
- UNC network shares supported
- Application state stored under the current Windows user's local application-data directory
- ROM library remains read-only unless explicitly required
- Hack library remains the writable game-library location
