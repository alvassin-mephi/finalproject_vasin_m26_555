.PHONY: help install run scheduler lint format build clean-logs clean-data

help:
	@echo "make install - install dependencies"
	@echo "make run - start the CLI"
	@echo "make scheduler - start periodic exchange rate updates"
	@echo "make lint - check code and formatting"
	@echo "make format - format code"
	@echo "make build - build the package"
	@echo "make clean-logs - remove logs and rotated archives"
	@echo "make clean-data - remove generated JSON data"

install:
	uv sync

run:
	uv run valutatrade

scheduler:
	uv run python -m valutatrade_hub.parser_service.scheduler

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .

build:
	uv build

clean-logs:
	rm -f logs/*.log logs/*.log.*

clean-data:
	rm -f data/*.json
