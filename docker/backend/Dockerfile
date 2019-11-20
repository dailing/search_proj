FROM ubuntu:18.04

ENV LANG=C.UTF-8 LC_ALL=C.UTF-8

WORKDIR /workspace

# RUN sed -i 's/http/https/g' /etc/apt/sources.list && \
RUN sed -i 's/archive.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list && \
    sed -i 's/security.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list

RUN DEBIAN_FRONTEND=noninteractive apt-get update && apt-get -y install --fix-missing wget curl tar\
    build-essential zlib1g-dev libffi-dev nodejs\
    libssl-dev libncurses5-dev libsqlite3-dev libreadline-dev libglib2.0-0 libsm-dev\
    libxrender-dev libxext-dev liblzma-dev libbz2-dev  libpq-dev redis fish zsh\
    chromium-browser chromium-chromedriver


RUN wget https://www.python.org/ftp/python/3.7.5/Python-3.7.5.tgz -O python.tgz &&\
    tar -xvf python.tgz && \
    cd Python-3.7.5 && ./configure --enable-optimizations && make -j20 install && \
    ln -sf /usr/local/bin/python3 /usr/local/bin/python && \
    ln -sf /usr/local/bin/pip3 /usr/local/bin/pip &&\
    cd .. && \
    rm * -rf

RUN pip3 config set global.index-url https://mirrors.aliyun.com/pypi/simple/

RUN pip3 install jupyterlab flask peewee psycopg2 flask-restful requests 
RUN pip3 install elasticsearch selenium BeautifulSoup4 pandas bibtexparser zerorpc

RUN useradd -m -U d
USER d

CMD "/workspace/run.sh"
