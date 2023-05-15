DOCKER_BUILDKIT=1
DOCKER_BUILD=docker buildx build

# Format: R{major}.{minor}.{micro}
EPICS_BASE_VERSION?=R7.0.2
# Format: YY.MM
BUILD_YY_MM?=23.05
# Format: N (not zero padded)
BUILD_NUMBER?=1
BASE_IMAGE_TAG=$(EPICS_BASE_VERSION)-${BUILD_YY_MM}-${BUILD_NUMBER}

SPECS=./specs/${BASE_IMAGE_TAG}
BASE_SPEC=$(SPECS)/base.yaml
MODULE_SPEC=$(SPECS)/modules.yaml

BUILD_ARGS= \
	--build-arg BASE_IMAGE_TAG=${BASE_IMAGE_TAG} \
	--build-arg SPECS=$(SPECS)

HOSTNAME?=ioc-tst-docker
RUN_ARGS?="--hostname=$(HOSTNAME)"

export DOCKER_BUILDKIT
export BASE_IMAGE_TAG

all: run-ioc

initialize:
	# git submodule update --init --recursive
	:

build-base: initialize docker/Dockerfile.base
	$(DOCKER_BUILD) \
		--tag pcdshub/pcds-ioc-base-rhel7:latest \
		--file docker/Dockerfile.base \
		.

build-pib: initialize docker/Dockerfile.pib pib/*
	$(DOCKER_BUILD) \
		--tag pcdshub/pib:latest \
		--file docker/Dockerfile.pib \
		.

build-epics: build-base docker/Dockerfile.epics-base $(BASE_SPEC)
	$(DOCKER_BUILD) \
		--tag pcdshub/pcds-epics-base-rhel7:${BASE_IMAGE_TAG} \
		$(BUILD_ARGS) \
		--file docker/Dockerfile.epics-base \
		.

build-modules: build-epics docker/Dockerfile.modules $(MODULE_SPEC)
	$(DOCKER_BUILD)  \
		--tag pcdshub/pcds-epics-modules-rhel7:${BASE_IMAGE_TAG} \
		--file docker/Dockerfile.modules \
		$(BUILD_ARGS) \
		.

build-softioc: build-modules docker/Dockerfile.softIoc
	$(DOCKER_BUILD) \
		--tag pcdshub/pcds-epics-softioc-rhel7:${BASE_IMAGE_TAG} \
		--file docker/Dockerfile.softIoc \
		$(BUILD_ARGS) \
		--progress=plain \
		.
	docker run --rm -v $(shell pwd)/pib:/pib -v $(shell pwd)/softIoc:/softioc \
		-it pcdshub/pcds-epics-softioc-rhel7:${BASE_IMAGE_TAG}

test:
	$(DOCKER_BUILD)  \
		--tag pcdshub/pcds-epics-softioc-rhel7:${BASE_IMAGE_TAG} \
		--file docker/Dockerfile.softIoc \
		$(BUILD_ARGS) \
		--progress=plain \
		.
	docker run --rm -v $(shell pwd)/pib:/pib \
		-v $(shell pwd)/softIoc:/softioc \
		-it pcdshub/pcds-epics-softioc-rhel7:${BASE_IMAGE_TAG}

run-ioc: build-modules
	docker run -it $(RUN_ARGS) pcdshub/pcds-ioc:latest

.PHONY: build-pib build-modules build-base build-epics initialize run-ioc all
