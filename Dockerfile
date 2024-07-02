FROM python:3.9-slim

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV TELEGRAM_BOT_TOKEN=7257445269:AAFXXiih3qD__im6aI-bUv_4682Gsh-jm8A
ENV SHODAN_API_KEYS=YaLNvFBVpaTrMkW829nATM3xRTvMaVsH
ENV GROUP_USERNAME=@Indian_hacker_group
ENV CHANNEL_USERNAME=@Falcon_Securitykkkii
ENV OWNER_ID=5460343986

CMD ["python", "app.py"]
