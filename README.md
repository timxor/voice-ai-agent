# voice-ai-agent

A **Realtime Voice AI Agent** that you can call and interact with at:

<a href="tel:+18722243989"><strong>+1 (872) 224-3989</strong></a>


Deployed endpoint:
[https://voice.timsiwula.com](https://voice.timsiwula.com)

This project demonstrates how to build a production-ready **conversational AI system** that integrates telephony with a real-time LLM voice agent. It showcases end-to-end voice interaction, structured data collection, external API integration, and simulated scheduling workflows—making it a strong example of applied AI/voice engineering.

## Summary

The Voice AI Agent enables patients to call a phone number and interact with an AI assistant capable of gathering intake information for a healthcare appointment.  
The agent conducts a natural conversation, validates critical details, and finalizes next steps—all without human intervention.  

**Key Features:**  
- Real-time two-way voice interaction powered by AI  
- Integration with Twilio for telephony  
- External API usage for address validation  
- Structured data collection with in-memory storage  
- Simulation of provider scheduling and availability  


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
