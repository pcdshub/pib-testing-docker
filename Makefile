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

RUN_BUILDER=docker run --rm -v $(shell pwd)/$(SPECS):/specs -t pcdshub/pib:latest
BUILDER_GET_BASE_PATH=yq -r '.modules[] | select(.name="epics-base") | .install_path' base.yaml
BUILDER_GET_BASE_VERSION=yq -r '.modules[] | select(.name="epics-base") | .git.tag' base.yaml

export DOCKER_BUILDKIT
export EPICS_BASE_VERSION
export EPICS_BASE_IMAGE_TAG

all: run-ioc

initialize:
	# git submodule update --init --recursive
	:

build-base: initialize docker/Dockerfile.base
	docker build --tag pcdshub/pcds-ioc-base-rhel7:latest --file docker/Dockerfile.base .

build-builder: initialize docker/Dockerfile.builder pib/*
	docker build --tag pcdshub/pib:latest --file docker/Dockerfile.builder .

build-epics: build-builder build-base docker/Dockerfile.epics-base $(BASE_SPEC)
	base_version=$(shell $(RUN_BUILDER) $(BUILDER_GET_BASE_VERSION)); \
	base_path=$(shell $(RUN_BUILDER) $(BUILDER_GET_BASE_PATH)); \
			echo "EPICS base: $${base_version} installed to $${base_path}}"; \
			docker build \
				--tag pcdshub/pcds-epics-base-rhel7:${EPICS_BASE_IMAGE_TAG} \
				--build-arg SPECS=$(SPECS) \
				--build-arg EPICS_BASE=$${base_path} \
				--build-arg EPICS_BASE_VERSION=$${base_version} \
				--file docker/Dockerfile.epics-base \
				.

build-modules: build-epics docker/Dockerfile.modules $(MODULE_SPEC)
	docker build  \
		--tag pcdshub/pcds-epics-modules-rhel7:${EPICS_BASE_IMAGE_TAG} \
		--build-arg EPICS_BASE_IMAGE_TAG=${EPICS_BASE_IMAGE_TAG} \
		--build-arg SPECS=$(SPECS) \
		--file docker/Dockerfile.modules \
		.

run-ioc: build-modules
	docker run -it $(RUN_ARGS) pcdshub/pcds-ioc:latest

test:
	docker build  \
		--tag test \
		--build-arg EPICS_BASE_IMAGE_TAG=${EPICS_BASE_IMAGE_TAG} \
		--build-arg SPECS=$(SPECS) \
		--file docker/Dockerfile.modules \
		--progress=plain \
		.
	docker run --rm -v $(shell pwd)/pib:/pib -v $(shell pwd)/softIoc:/softioc -it test

.PHONY: build-builder build-modules build-base build-epics initialize run-ioc all
