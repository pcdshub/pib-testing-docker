# syntax=docker/dockerfile:1.4
# vi: syntax=Dockerfile

FROM python:3.10.9-bullseye

RUN apt-get -y update && \
      apt-get -y install jq && \
      apt-get clean

COPY pcds_ioc_builder /usr/local/src/pcds-ioc-builder
RUN python -m pip install /usr/local/src/pcds-ioc-builder
RUN rm -rf /usr/local/src/pcds-ioc-builder

WORKDIR /specs

CMD ["/bin/bash", "-c"]
