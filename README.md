# voice-ai-agent

A realtime voice AI scheduling agent built with Twilio Voice, OpenAI Realtime API, Python/FastAPI, WebSockets, DigitalOcean, and Resend.

> Demo phone number and deployed endpoint are currently disabled to avoid ongoing Twilio/cloud costs. The full implementation is available in this repository.

## Summary

This project demonstrates how to build a production-style conversational AI system that integrates telephony with a realtime LLM voice agent.

The Voice AI Agent handles an inbound phone call end-to-end: Twilio webhook routing, realtime audio streaming, AI conversation handling, structured data collection, simulated scheduling logic, and appointment confirmation email delivery.

It is designed to showcase applied voice AI engineering concepts including low-latency audio interaction, turn-taking, session state management, OpenAI function calling, external API integration, and reliable workflow completion.

## Key Features

- Realtime two-way voice interaction using Twilio Voice and OpenAI Realtime API
- Python/FastAPI backend with WebSocket-based audio streaming
- Structured intake data extraction using OpenAI function calling
- Session-based call state management
- Simulated provider availability and appointment scheduling workflow
- Automated appointment confirmation emails via Resend API
- Deployment-ready architecture using DigitalOcean
- Practical handling of latency, interruptions, fallbacks, and end-to-end call completion


## Quick Start

## Clone and setup virtual environment
```
git clone https://github.com/timxor/voice-ai-agent.git
cd voice-ai-agent

python -m venv .venv
source .venv/bin/activate

cp env.example .env

python -m pip install -U -r requirements.txt
python main.py
```

## Python version
```
# python version should be 3.14.4 to match the .python-version file for pyenv
cat .python-version

# download and set current version to 3.14.4
pyenv install 3.14.4
pyenv local 3.14.4

python --version
# Python 3.14.4
```

## Setup API keys
```
cp env.example .env

cat env.example

nano .env

HOST=timxor.ngrok.io
OPENAI_API_KEY=openai_****************************

RESEND_API_KEY=resend_********************************
RESEND_FROM=updates@updates.timsiwula.com

EMAIL_RECIPIENTS="siwulactim@gmail.com,cpliang.doris@gmail.com"
GEOAPIFY_API_KEY=your_api_key
```

## Start server in terminal screen 1
```
python main.py
```

## Expose server with ngrok in terminal screen 2
```
ngrok http --url=timxor.ngrok.io 8080
```

## Twilio configuration

```
My Twilio phone number: 872-335-4559

My Twilio voice webhook: https://timxor.ngrok.io/incoming-call

Twilio: Point your phone number’s Voice webhook to https://your.public.host/incoming-call.

Twilio number voice configuration: https://console.twilio.com/us1/develop/phone-numbers/manage/incoming/PN3a1f292d0ae6099cbda251ad19817f19/configure
```


## Ngrok configuration

```
My Ngrok local development reverse proxy for the voice webhook: https://timxor.ngrok.io/incoming-call

Start ngrok:
ngrok http --url=timxor.ngrok.io 8080

```

Verify ngrok redirect is working:
[https://timxor.ngrok.io/incoming-call](https://timxor.ngrok.io/incoming-call)
