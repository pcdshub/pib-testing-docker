DOCKER_BUILDKIT=1
HOSTNAME?=ioc-tst-docker
RUN_ARGS?="--hostname=$(HOSTNAME)"

EPICS_BASE_VERSION=R7.0.2-2.0.1
EPICS_BASE_BUILD_NUMBER=1
EPICS_BASE_IMAGE_TAG=$(EPICS_BASE_VERSION)_v${EPICS_BASE_BUILD_NUMBER}

SPECS=./specs/${EPICS_BASE_IMAGE_TAG}
BASE_SPEC=$(SPECS)/base.yaml
MODULE_SPEC=$(SPECS)/modules.yaml

export DOCKER_BUILDKIT
export EPICS_BASE_IMAGE_TAG

all: run-ioc

initialize:
	# git submodule update --init --recursive
	:

build-base: initialize docker/Dockerfile.base
	docker build \
		--tag pcdshub/pcds-ioc-base-rhel7:latest \
		--file docker/Dockerfile.base \
		.

build-pib: initialize docker/Dockerfile.pib pib/*
	docker build \
		--tag pcdshub/pib:latest \
		--file docker/Dockerfile.pib \
		.

build-epics: build-base docker/Dockerfile.epics-base $(BASE_SPEC)
	docker build \
		--tag pcdshub/pcds-epics-base-rhel7:${EPICS_BASE_IMAGE_TAG} \
		--build-arg SPECS=$(SPECS) \
		--file docker/Dockerfile.epics-base \
		.

build-modules: build-epics docker/Dockerfile.modules $(MODULE_SPEC)
	docker build  \
		--tag pcdshub/pcds-epics-modules-rhel7:${EPICS_BASE_IMAGE_TAG} \
		--build-arg EPICS_BASE_IMAGE_TAG=${EPICS_BASE_IMAGE_TAG} \
		--build-arg SPECS=$(SPECS) \
		--file docker/Dockerfile.modules \
		.

build-softioc: build-modules docker/Dockerfile.softIoc
	docker build  \
		--tag pcdshub/pcds-epics-softioc-rhel7:${EPICS_BASE_IMAGE_TAG} \
		--build-arg EPICS_BASE_IMAGE_TAG=${EPICS_BASE_IMAGE_TAG} \
		--build-arg SPECS=$(SPECS) \
		--file docker/Dockerfile.softIoc \
		--progress=plain \
		.
	docker run --rm -v $(shell pwd)/pib:/pib -v $(shell pwd)/softIoc:/softioc \
		-it pcdshub/pcds-epics-softioc-rhel7:${EPICS_BASE_IMAGE_TAG}

test:
	docker build  \
		--tag pcdshub/pcds-epics-softioc-rhel7:${EPICS_BASE_IMAGE_TAG} \
		--build-arg EPICS_BASE_IMAGE_TAG=${EPICS_BASE_IMAGE_TAG} \
		--build-arg SPECS=$(SPECS) \
		--file docker/Dockerfile.softIoc \
		--progress=plain \
		.
	docker run --rm -v $(shell pwd)/pib:/pib \
		-v $(shell pwd)/softIoc:/softioc \
		-it pcdshub/pcds-epics-softioc-rhel7:${EPICS_BASE_IMAGE_TAG}

run-ioc: build-modules
	docker run -it $(RUN_ARGS) pcdshub/pcds-ioc:latest

.PHONY: build-pib build-modules build-base build-epics initialize run-ioc all
