# L&T Group CHRO fixtures

OE-shaped packs consumed by `backend/app/fixtures/lnt_loader.py`.

```
seed/
  lnt_group/          Group workspace profile, people, departments, memory, docs
  companies/
    lnt_finance/      LTF
    lnt_metro_rail/   LTMR
    lnt_realty/       LTR
    lnt_technology_services/  LTTS
    ltimindtree/      LTIM
```

Load:

```bash
cd backend
uv run python -m scripts.seed_lnt --reset
# or POST /fixtures/lnt/load (admin)
```
