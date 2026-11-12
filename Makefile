.PHONY: help install install-dev build binary clean uninstall test

PYTHON ?= python3
PIP ?= pip3
PREFIX ?= $(HOME)/.local
BINDIR ?= $(PREFIX)/bin

help:
	@echo "ncdeck Makefile"
	@echo ""
	@echo "Available targets:"
	@echo "  install      Install ncdeck system-wide/user (uses pip)"
	@echo "  install-dev  Install in development mode"
	@echo "  build        Build distribution packages (wheel + sdist)"
	@echo "  binary       Build a standalone PyInstaller binary in dist/"
	@echo "  clean        Remove build artifacts"
	@echo "  uninstall    Uninstall ncdeck"
	@echo "  install-bin  Install just the script to ~/.local/bin"
	@echo ""

install:
	$(PIP) install .

install-dev:
	$(PIP) install -e .

build:
	$(PIP) install --upgrade build
	$(PYTHON) -m build

binary:
	bash scripts/build-binary.sh

clean:
	rm -rf build/ dist/ .build-venv/ *.egg-info src/*.egg-info .pytest_cache/ *.spec
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete

uninstall:
	$(PIP) uninstall -y ncdeck

install-bin:
	mkdir -p $(BINDIR)
	cp src/ncdeck/cli.py $(BINDIR)/ncdeck
	chmod +x $(BINDIR)/ncdeck
	@echo "Installed to $(BINDIR)/ncdeck"
	@echo "Make sure $(BINDIR) is in your PATH"

install-config:
	mkdir -p $(HOME)/.config/ncdeck
	@if [ ! -f $(HOME)/.config/ncdeck/config.yaml ]; then \
		cp config.example.yaml $(HOME)/.config/ncdeck/config.yaml; \
		echo "Created $(HOME)/.config/ncdeck/config.yaml"; \
	else \
		echo "Config already exists at $(HOME)/.config/ncdeck/config.yaml"; \
	fi
