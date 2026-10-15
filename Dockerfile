FROM debian:trixie-slim@sha256:a29215f6a35e51e22adffa17f89e9d2ef06214e64a2bad10d765c46aea49f11f AS toolchain

ENV DEBIAN_FRONTEND=noninteractive

ARG DEBIAN_SNAPSHOT=20261005T000000Z

RUN sed -i \
      -e "s|^URIs: http://deb.debian.org/debian\$|URIs: http://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}|" \
      -e "s|^URIs: http://deb.debian.org/debian-security\$|URIs: http://snapshot.debian.org/archive/debian-security/${DEBIAN_SNAPSHOT}|" \
      /etc/apt/sources.list.d/debian.sources \
 && grep -q "snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}" /etc/apt/sources.list.d/debian.sources \
 && apt-get -o Acquire::Check-Valid-Until=false update \
 && apt-get install -y --no-install-recommends \
      build-essential=12.12 \
      ca-certificates=20250419 \
      cppcheck=2.17.1-2 \
      git=1:2.47.3-0+deb13u1 \
      make=4.4.1-2 \
      python3=3.13.5-1 \
      python-is-python3=3.13.3-1 \
      sdcc=4.5.0+dfsg-1 \
 && rm -rf /var/lib/apt/lists/*

ARG DEVKITSMS_REF=86a24d36d4c940678edb307ad30579e40bbae4e2

RUN git clone https://github.com/sverx/devkitSMS.git /opt/devkitSMS \
 && git -C /opt/devkitSMS checkout --quiet "${DEVKITSMS_REF}" \
 && cc -O2 -o /usr/local/bin/ihx2sms /opt/devkitSMS/ihx2sms/src/ihx2sms.c \
 && cc -O2 -o /usr/local/bin/folder2c /opt/devkitSMS/folder2c/src/folder2c.c \
 && install -m 0755 /opt/devkitSMS/assets2banks/src/assets2banks.py /usr/local/bin/assets2banks

RUN make -C /opt/devkitSMS/crt0/src \
 && make -C /opt/devkitSMS/SMSlib/src CONFIG="--sdcccall 1" \
 && install -m 0644 /opt/devkitSMS/SMSlib/src/SMSlib.lib /opt/devkitSMS/SMSlib/SMSlib.lib \
 && install -m 0644 /opt/devkitSMS/crt0/src/crt0_sms.rel /opt/devkitSMS/crt0/crt0_sms.rel

ENV DEVKITSMS=/opt/devkitSMS
ENV SMSLIB=/opt/devkitSMS/SMSlib
ENV CRT0=/opt/devkitSMS/crt0

WORKDIR /work
