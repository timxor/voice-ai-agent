# voice-ai-agent

A **Realtime Voice AI Agent** that you can call and interact with at:
<a href="tel:+18722243989"><strong>+1 (872) 224-3989</strong></a>

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

```
git clone https://github.com/timxor/voice-ai-agent.git
cd voice-ai-agent


python -m venv env
source env/bin/activate
pip install -r requirements.txt

python main.py


cp env.dev.example > .env


# then open .env
# and set your api keys:

OPENAI_API_KEY=openai_****************************
RESEND_API_KEY=re_********************************
RESEND_FROM=updates@updates.timsiwula.com
GEOAPIFY_API_KEY=your_api_key


# server and websocket running at:
http://127.0.0.1:8080

# incoming call endpoint running at:
http://127.0.0.1:8080/incoming-call

```


### voice agents api example

```
python voice_agents_api_example.py
```

### agents api example

```
python agents_api_example.py
```
