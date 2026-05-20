## 1. Create job folder structure

- [x] 1.1 Create `jobs/test_simple/` with `__init__.py`, `job.py`, `items.py`, `config.yaml`
- [x] 1.2 Create `jobs/test_flaky/` with `__init__.py`, `job.py`, `items.py`, `config.yaml`
- [x] 1.3 Create `jobs/test_setup/` with `__init__.py`, `job.py`, `items.py`, `config.yaml`

## 2. Migrate code into job folders

- [x] 2.1 Move `jobs/test/square.py` logic into `jobs/test_simple/job.py`
- [x] 2.2 Move `insertions/test/range_items.py` logic into `jobs/test_simple/items.py`
- [x] 2.3 Move `jobs/test/flaky.py` logic into `jobs/test_flaky/job.py`
- [x] 2.4 Move `insertions/test/flaky_items.py` logic into `jobs/test_flaky/items.py`
- [x] 2.5 Move `jobs/test/with_setup.py` logic into `jobs/test_setup/job.py`
- [x] 2.6 Copy `insertions/test/range_items.py` logic into `jobs/test_setup/items.py`

## 3. Create config files with updated paths

- [x] 3.1 Write `jobs/test_simple/config.yaml` with dotted paths to colocated modules
- [x] 3.2 Write `jobs/test_flaky/config.yaml` with dotted paths to colocated modules
- [x] 3.3 Write `jobs/test_setup/config.yaml` with dotted paths to colocated modules (including setup field)

## 4. Update runner and justfile

- [x] 4.1 Update justfile `run` recipe to resolve `jobs/{{config}}/config.yaml`
- [x] 4.2 Update justfile shorthand commands (`test-simple`, etc.) to use new paths
- [x] 4.3 Update justfile `submit` recipe to use new config path pattern

## 5. Remove old directories

- [x] 5.1 Remove `configs/` directory
- [x] 5.2 Remove `insertions/` directory
- [x] 5.3 Remove `jobs/test/` directory (old location)

## 6. Verify

- [x] 6.1 Run `just test-simple` and confirm success
- [x] 6.2 Run `just test-failure` and confirm expected failures
- [x] 6.3 Run `just test-setup` and confirm setup phase works
