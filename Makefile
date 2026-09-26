.PHONY: check test demo serve deadcode

check:
	python -m compileall -q hydrorefuel
	python tools/deadcode.py hydrorefuel

test:
	PYTHONPATH=. python -m pytest -q

run:
	PYTHONPATH=. python -m hydrorefuel --config config/hydrorefuel.json serve --host 127.0.0.1 --port 8080

demo:
	PYTHONPATH=. python -m hydrorefuel --config config/hydrorefuel.json demo --fast --vehicles 2

deadcode:
	PYTHONPATH=. python tools/deadcode.py hydrorefuel
