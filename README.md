# voice-ai-agent

Voice AI Agent that handles Twilio calls




## Call the Voice AI Agent


Try calling it and scheduling an appointment, the number is +1 (872) 224-3989


## Requirements

https://assort.notion.site/Assort-Health-Take-Home-Assignment-1c20b294614648bab39b1d4dafd6a40d



## Quick Start

```
git clone https://github.com/timxor/voice-ai-agent.git
cd voice-ai-agent

cp env.dev.example > .env


# then open .env
# and set your api keys:

OPENAI_API_KEY=openai_****************************
RESEND_API_KEY=re_********************************
RESEND_FROM=you@yourdomain.com
GEOAPIFY_API_KEY=your_api_key


python3 -m venv env
source env/bin/activate
pip install -r requirements.txt

# run app
python main.py

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
