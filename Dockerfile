FROM rockylinux:8

RUN yum -y update
RUN yum -y install python39 python39-pip
RUN pip3 install --upgrade pip
RUN pip3 install openai slack-sdk slack-bolt tiktoken
RUN mkdir -p /opt/gpt-chatter
COPY gpt-chatter-slack.py /root
WORKDIR /root
CMD ["python3", "gpt-chatter-slack.py"]
