DOCKER_BUILDKIT=1
HOSTNAME?=ioc-tst-docker
RUN_ARGS?="--hostname=$(HOSTNAME)"

# TODO: directory may differ from the version tag on our current
# filesystem. Keeping that inconsistency so that paths may be the same,
# at least for now...
EPICS_BASE_VERSION=R7.0.2-2.0.1
EPICS_BASE_BUILD_NUMBER=1
EPICS_BASE_IMAGE_TAG=$(EPICS_BASE_VERSION)_v${EPICS_BASE_BUILD_NUMBER}

SPECS=./specs/${EPICS_BASE_IMAGE_TAG}
BASE_SPEC=$(SPECS)/base.yaml
MODULE_SPEC=$(SPECS)/modules.yaml

RUN_BUILDER=docker run --rm  -v $(shell pwd)/$(SPECS):/specs -t pcdshub/pcds-ioc-builder:latest

export DOCKER_BUILDKIT
export EPICS_BASE_VERSION
export EPICS_BASE_IMAGE_TAG

all: run-ioc

initialize:
	# git submodule update --init --recursive
	:

build-base: initialize docker/Dockerfile.base
	docker build --tag pcdshub/pcds-ioc-base:latest --file docker/Dockerfile.base .

build-builder: initialize docker/Dockerfile.builder builder/*
	docker build --tag pcdshub/pcds-ioc-builder:latest --file docker/Dockerfile.builder .

build-epics: build-builder build-base docker/Dockerfile.epics-base $(BASE_SPEC)
	docker build \
		--tag pcdshub/pcds-epics-base:${EPICS_BASE_IMAGE_TAG} \
		--build-arg SPECS=$(SPECS) \
		--build-arg EPICS_BASE_DIR=$(shell $(RUN_BUILDER) yq -r '.modules["epics-base"].install_path' base.yaml) \
		--build-arg EPICS_BASE_VERSION=$(shell $(RUN_BUILDER) yq -r '.modules["epics-base"].git.tag' base.yaml) \
		--file docker/Dockerfile.epics-base \
		.

build-modules: build-epics docker/Dockerfile.modules $(MODULE_SPEC)
	docker build  \
		--build-arg EPICS_BASE_IMAGE_TAG=${EPICS_BASE_IMAGE_TAG} \
		--build-arg SPECS=$(SPECS) \
		--file docker/Dockerfile.modules \
		.

run-ioc: build-modules
	docker run -it $(RUN_ARGS) pcdshub/pcds-ioc:latest

test:
	docker build  \
		--build-arg EPICS_BASE_IMAGE_TAG=${EPICS_BASE_IMAGE_TAG} \
		--build-arg SPECS=$(SPECS) \
		--file docker/Dockerfile.softIoc \
		.

.PHONY: build-builder build-modules build-base build-epics initialize run-ioc all
