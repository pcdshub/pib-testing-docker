DOCKER_BUILDKIT=1
HOSTNAME?=ioc-tst-docker
RUN_ARGS?="--hostname=$(HOSTNAME)"

# TODO: directory may differ from the version tag on our current
# filesystem. Keeping that inconsistency so that paths may be the same,
# at least for now...
EPICS_BASE_DIR=R7.0.2-2.0
EPICS_BASE_VERSION=R7.0.2-2.0.1
EPICS_BASE_BUILD_NUMBER=0
EPICS_BASE_IMAGE_TAG=$(EPICS_BASE_VERSION)_v${EPICS_BASE_BUILD_NUMBER}

export DOCKER_BUILDKIT
export EPICS_BASE_DIR
export EPICS_BASE_VERSION
export EPICS_BASE_IMAGE_TAG

all: run-ioc

initialize:
	# git submodule update --init --recursive
	:

build-base: initialize docker/Dockerfile.base
	docker build --tag pcdshub/pcds-ioc-machine-base:latest --file docker/Dockerfile.base .

build-epics: build-base docker/Dockerfile.epics-base
	docker build \
		--tag pcdshub/pcds-epics-base:latest \
		--tag pcdshub/pcds-epics-base:${EPICS_BASE_IMAGE_TAG} \
		--build-arg EPICS_BASE_DIR=${EPICS_BASE_DIR} \
		--build-arg EPICS_BASE_VERSION=${EPICS_BASE_VERSION} \
		--file docker/Dockerfile.epics-base \
		.

build-modules: build-base build-epics docker/Dockerfile.modules
	docker build  \
		--tag pcdshub/pcds-ioc:latest \
		--build-arg EPICS_BASE_IMAGE_TAG=${EPICS_BASE_IMAGE_TAG} \
		--build-arg MODULE_FILE=modules/${EPICS_BASE_VERSION}.yaml \
		--file docker/Dockerfile.modules \
		.

run-ioc: build-softioc
	docker run -it $(RUN_ARGS) pcdshub/pcds-ioc:latest

.PHONY: build-softioc build-base build-epics initialize run-ioc all
