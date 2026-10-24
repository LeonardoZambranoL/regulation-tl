PYTHON := ../../../.venv/bin/python

.PHONY: audit test dev holdout eval ablate

audit:
	$(PYTHON) scripts/inspect_data.py

test:
	$(PYTHON) -m unittest discover -s tests -p "test_*.py" -v

dev:
	$(PYTHON) -m certi.run --case dev-rear-lamp --out outputs/predictions.json
	$(PYTHON) scripts/eval_main.py outputs/predictions.json --case dev-rear-lamp

holdout:
	$(PYTHON) -m certi.run --case holdout-acpe --out outputs/predictions-holdout-acpe.json
	$(PYTHON) scripts/eval_main.py outputs/predictions-holdout-acpe.json --case holdout-acpe

ablate:
	$(PYTHON) scripts/ablate.py
