TEST?=ralph
TEST_ARGS=
DOCKER_REPO_NAME?="allegro"
RALPH_VERSION?=$(shell git describe --abbrev=0)
PYTHON_BIN?=python3.10
VENV_DIR?=venv
VENV_PIP=$(VENV_DIR)/bin/pip
VENV_PYTHON=$(VENV_DIR)/bin/python
DATABASE_NAME?=ralph_ng
DATABASE_USER?=ralph_ng
DATABASE_TEST_NAME?=test_$(DATABASE_NAME)

COMPOSE?=docker compose
STACK_COMPOSE_FILE?=docker/docker-compose-local-dev.yml
STACK_WEB_SERVICE?=assets-web
STACK_DB_SERVICE?=assets-db
TMP_LOG_DIR?=tmp/logs
LOGS_TAIL?=200
FRONTEND_TEST?=npm run test
CONTAINER_SHELL?=/bin/sh -lc
MIGRATE_CMD?=ralph migrate --noinput
SITETREE_CMD?=ralph sitetree_resync_apps
DB_WAIT_RETRIES?=24
DB_WAIT_SLEEP?=5
export DB_WAIT_RETRIES
export DB_WAIT_SLEEP
DB_WAIT_CMD?=cd /opt/sirius-ralph && \
  DB_WAIT_RETRIES=$(DB_WAIT_RETRIES) DB_WAIT_SLEEP=$(DB_WAIT_SLEEP) scripts/wait_for_db.sh

.PHONY: test flake clean clean-pyc stack-clean coverage docs coveralls venv venv-install-dev venv-clean up down logs

# release-new-version is used by ralph mainteiners prior to publishing
# new version of the package. The command generates the debian changelog
# commits it and tags the created commit with the appropriate snapshot version.
release-new-version: new_version = $(shell ./get_version.sh generate)
release-new-version:
	docker build \
		--force-rm \
		-f docker/Dockerfile-deb \
		--build-arg GIT_USER_NAME="$(shell git config user.name)" \
		--build-arg GIT_USER_EMAIL="$(shell git config user.email)" \
		-t ralph-deb:latest .
	docker run --rm -it -v $(shell pwd):/volume ralph-deb:latest release-new-version
	docker image rm --force ralph-deb:latest
	git add debian/changelog
	git commit -m "Updated changelog for $(new_version) version."
	git tag -m $(new_version) -a $(new_version)

# build-package builds a release version of the package using the generated
# changelog and the tag.
build-package:
	docker build --force-rm -f docker/Dockerfile-deb -t ralph-deb:latest .
	docker run --rm -v $(shell pwd):/volume ralph-deb:latest build-package
	docker image rm --force ralph-deb:latest

# build-snapshot-package renerates a snapshot changelog and uses it to build
# snapshot version of the package. It is mainly used for testing.
build-snapshot-package:
	docker build --force-rm -f docker/Dockerfile-deb -t ralph-deb:latest .
	docker run --rm -v $(shell pwd):/volume ralph-deb:latest build-snapshot-package
	docker image rm --force ralph-deb:latest

build-docker-image:
	docker build \
		--no-cache \
		-f docker/Dockerfile-prod \
		--build-arg RALPH_VERSION="$(RALPH_VERSION)" \
		-t $(DOCKER_REPO_NAME)/ralph:latest \
		-t "$(DOCKER_REPO_NAME)/ralph:$(RALPH_VERSION)" .
	docker build \
		-f docker/Dockerfile-inkpy \
		-t "$(DOCKER_REPO_NAME)/inkpy:$(RALPH_VERSION)" .
	docker build \
		--no-cache \
		-f docker/Dockerfile-static \
		--build-arg RALPH_VERSION="$(RALPH_VERSION)" \
		-t $(DOCKER_REPO_NAME)/ralph-static-nginx:latest \
		-t "$(DOCKER_REPO_NAME)/ralph-static-nginx:$(RALPH_VERSION)" .

build-snapshot-docker-image: version = $(shell ./get_version.sh show)
build-snapshot-docker-image: build-snapshot-package
	docker build \
		-f docker/Dockerfile-prod \
		--build-arg RALPH_VERSION="$(version)" \
		--build-arg SNAPSHOT="1" \
		-t $(DOCKER_REPO_NAME)/ralph:latest \
		-t "$(DOCKER_REPO_NAME)/ralph:$(version)" .
	docker build \
		-f docker/Dockerfile-inkpy \
		-t "$(DOCKER_REPO_NAME)/inkpy:$(version)" .
	docker build \
		-f docker/Dockerfile-static \
		--build-arg RALPH_VERSION="$(version)" \
		-t "$(DOCKER_REPO_NAME)/ralph-static-nginx:$(version)" .

publish-docker-image: build-docker-image
	docker push $(DOCKER_REPO_NAME)/ralph:$(RALPH_VERSION)
	docker push $(DOCKER_REPO_NAME)/ralph:latest
	docker push $(DOCKER_REPO_NAME)/ralph-static-nginx:$(RALPH_VERSION)
	docker push $(DOCKER_REPO_NAME)/ralph-static-nginx:latest
	docker push $(DOCKER_REPO_NAME)/inkpy:$(RALPH_VERSION)

publish-docker-snapshot-image: version = $(shell ./get_version.sh show)
publish-docker-snapshot-image: build-snapshot-docker-image
	docker push $(DOCKER_REPO_NAME)/ralph:$(version)
	docker push $(DOCKER_REPO_NAME)/inkpy:$(version)
	docker push $(DOCKER_REPO_NAME)/ralph-static-nginx:$(version)

install-js:
	npm install
	./node_modules/.bin/gulp

js-hint:
	find src/ralph|grep "\.js$$"|grep -v vendor|xargs ./node_modules/.bin/jshint;

install: install-js
	pip3 install -r requirements/prod.txt

install-test:
	pip3 install -r requirements/test.txt

install-dev:
	pip3 install -r requirements/dev.txt

install-docs:
	pip3 install -r requirements/docs.txt

venv:
	test -d $(VENV_DIR) || $(PYTHON_BIN) -m venv $(VENV_DIR)
	$(VENV_PIP) install --upgrade pip setuptools wheel

venv-install-dev: venv
	$(VENV_PIP) install -r requirements/dev.txt
	$(VENV_PIP) install -e .

venv-clean:
	rm -rf $(VENV_DIR)

isort:
	isort --diff --recursive --check-only --quiet src

test: clean
	test_ralph test $(TEST) $(TEST_ARGS)

flake: isort
	flake8 src/ralph
	flake8 src/ralph/settings --ignore=F405 --exclude=*local.py
	@cat scripts/flake.txt

checks:
	ruff check src

clean: clean-pyc stack-clean

clean-pyc:
	find . -name '*.py[cod]' -delete;

stack-clean:
ifeq ($(SKIP_STACK_CLEAN),)
	$(COMPOSE) -f $(STACK_COMPOSE_FILE) down --volumes --remove-orphans --rmi all || true
	rm -rf $(TMP_LOG_DIR)
else
	@echo "Skipping stack cleanup (SKIP_STACK_CLEAN=$(SKIP_STACK_CLEAN))"
endif

coverage: clean
	coverage run $(shell which test_ralph) test $(TEST) -v 2 --keepdb --settings="ralph.settings.test"
	coverage report

docs: install-docs
	mkdocs build

run:
	dev_ralph runserver_plus 0.0.0.0:8000

menu:
	ralph sitetree_resync_apps

translate_messages:
	ralph makemessages -a

compile_messages:
	ralph compilemessages

up:
	mkdir -p $(TMP_LOG_DIR)
	$(COMPOSE) -f $(STACK_COMPOSE_FILE) up --build -d
	$(COMPOSE) -f $(STACK_COMPOSE_FILE) exec -T $(STACK_WEB_SERVICE) $(CONTAINER_SHELL) "$(DB_WAIT_CMD)"
	$(COMPOSE) -f $(STACK_COMPOSE_FILE) exec -T $(STACK_WEB_SERVICE) $(CONTAINER_SHELL) "$(MIGRATE_CMD)"
	$(COMPOSE) -f $(STACK_COMPOSE_FILE) exec -T $(STACK_DB_SERVICE) /bin/sh -lc "mysql -uroot -p\$$MYSQL_ROOT_PASSWORD -e \"DROP DATABASE IF EXISTS $(DATABASE_TEST_NAME); GRANT ALL PRIVILEGES ON $(DATABASE_TEST_NAME).* TO '$(DATABASE_USER)'@'%'; GRANT CREATE, DROP ON *.* TO '$(DATABASE_USER)'@'%'; FLUSH PRIVILEGES;\""
	$(COMPOSE) -f $(STACK_COMPOSE_FILE) exec -T $(STACK_WEB_SERVICE) $(CONTAINER_SHELL) "$(SITETREE_CMD)"

down:
	$(COMPOSE) -f $(STACK_COMPOSE_FILE) down --remove-orphans

logs:
	mkdir -p $(TMP_LOG_DIR)
	$(COMPOSE) -f $(STACK_COMPOSE_FILE) ps | tee $(TMP_LOG_DIR)/docker-ps.log
	$(COMPOSE) -f $(STACK_COMPOSE_FILE) logs --tail=$(LOGS_TAIL) | tee $(TMP_LOG_DIR)/docker-compose.log
	@set -o pipefail; $(FRONTEND_TEST) | tee $(TMP_LOG_DIR)/frontend-test.log
ifneq ($(WATCH),)
	@echo "Streaming docker logs (Ctrl+C to stop)…"
	$(COMPOSE) -f $(STACK_COMPOSE_FILE) logs -f | tee -a $(TMP_LOG_DIR)/docker-compose.log
endif
