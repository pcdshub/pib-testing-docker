# syntax=docker/dockerfile:1.4
# vi: syntax=Dockerfile

FROM python:3.10.9-bullseye

RUN apt-get -y update && \
      apt-get -y install jq && \
      apt-get clean

COPY pib /usr/local/src/pib
RUN python -m pip install /usr/local/src/pib
RUN rm -rf /usr/local/src/pib

WORKDIR /specs

CMD ["/bin/bash", "-c"]
