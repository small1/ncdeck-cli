# Third-party notices

The standalone `ncdeck` binaries bundle the Python runtime and the following
third-party packages. `ncdeck` itself is licensed **GPL-3.0-only** (see
[LICENSE](LICENSE)); the bundled components keep their own licenses.

| Component | License | Used for |
| --- | --- | --- |
| Python (CPython) | PSF License | Embedded runtime |
| [click](https://pypi.org/project/click/) | BSD-3-Clause | CLI parsing and terminal styling |
| [requests](https://pypi.org/project/requests/) | Apache-2.0 | Nextcloud HTTP API calls |
| [PyYAML](https://pypi.org/project/PyYAML/) | MIT | Config file reading/writing |
| [certifi](https://pypi.org/project/certifi/) | MPL-2.0 | CA certificates for HTTPS |
| [charset-normalizer](https://pypi.org/project/charset-normalizer/) | MIT | Response encoding detection |
| [idna](https://pypi.org/project/idna/) | BSD-3-Clause | Internationalized domain names |
| [urllib3](https://pypi.org/project/urllib3/) | MIT | HTTP connection pooling |
| [PyInstaller bootloader](https://pyinstaller.org/) | GPL-2.0 **with linking exception** | Self-extracting launcher; the exception permits distributing binaries under other licenses |

Full license texts are included in the installed distributions of each package
and are available from the project links above. When building from source,
`pip install -r requirements.txt` installs these packages with their license
files.

> **Note:** no third-party command-line tools are required at runtime. File
> attachments are uploaded in-process with `requests` (`curl` is not used), and
> the login flow opens the OS's default browser via its standard URL handler
> rather than Python's browser-detection heuristics.
