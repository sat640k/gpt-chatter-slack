FROM rockylinux:9

RUN yum -y update && \
    yum -y install python3 python3-pip
#RUN dnf -qy module disable postgresql

RUN ARCH=$(uname -m) && dnf install -y https://download.postgresql.org/pub/repos/yum/reporpms/EL-9-${ARCH}/pgdg-redhat-repo-latest.noarch.rpm
RUN dnf install -y postgresql14 postgresql14-devel

RUN pip3 install --upgrade pip && \
    pip3 install openai slack-sdk slack-bolt tiktoken && \
    pip3 install sqlmodel sqlite-utils pg8000
RUN mkdir -p /opt/gpt-chatter
COPY gpt-chatter-slack.py /root/
COPY model.py /root/
WORKDIR /root
CMD ["python3", "gpt-chatter-slack.py"]
