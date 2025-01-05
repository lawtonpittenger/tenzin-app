# PURPOSE: This Dockerfile will prepare an Amazon Linux docker image with everything needed to create
# an AWS Lambda layer with MediaInfo libraries and pymediainfo package for Python 3.8 and Python 3.9
# USAGE:
# 1. Build the docker image:
#     docker build --tag=pymediainfo-layer-factory:latest . --no-cache
# 2. Extrack Zip archive ./pymediainfo-python.zip with pymediainfo package and MediaInfo library
#     docker run --rm -it -v $(pwd):/data pymediainfo-layer-factory cp /packages/pymediainfo-layer.zip /data

FROM amazonlinux

WORKDIR /
RUN yum update -y
RUN yum install gcc gcc-c++ openssl-devel bzip2-devel libffi-devel wget tar unzip gzip zip make -y
RUN yum install libjpeg-devel zlib-devel libtiff-devel freetype-devel lcms2-devel libwebp-devel tcl-devel tk-devel -y

# Install Python 3.9
WORKDIR /
RUN wget https://www.python.org/ftp/python/3.9.15/Python-3.9.15.tgz
RUN tar -xzf Python-3.9.15.tgz
WORKDIR /Python-3.9.15
RUN yum install -y zlib-devel
RUN ./configure --enable-optimizations
RUN make install

# Install Python packages
RUN mkdir /packages
COPY requirements.txt /packages/
RUN pip3.9 install --upgrade pip
RUN pip3.9 install -r /packages/requirements.txt -t /packages/python/lib/python3.9/site-packages

# Download MediaInfo
WORKDIR /root
RUN wget https://mediaarea.net/download/binary/libmediainfo0/22.09/MediaInfo_DLL_22.09_Lambda_x86_64.zip
RUN unzip -j MediaInfo_DLL_22.09_Lambda_x86_64.zip LICENSE
RUN unzip -j MediaInfo_DLL_22.09_Lambda_x86_64.zip lib/libmediainfo.so.0.0.0

# Create zip file for Lambda Layer deployment
RUN cp /root/LICENSE /packages/LICENSE
RUN cp /root/libmediainfo.so.0.0.0 /packages/libmediainfo.so
WORKDIR /packages
RUN zip -r9 /packages/pymediainfo-layer.zip .