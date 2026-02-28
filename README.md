# 🎧 AuraCast: Your Books, Turned into AI Podcasts

Hi! 👋 I'm Ivy, and welcome to AuraCast. 

I built this project for my CMU 15-113 class because I wanted a more engaging way to digest long-form text. AuraCast is a full-stack web app that takes your eBooks (EPUBs or PDFs) and transforms them into an interactive, two-host podcast. 

It doesn't just read the book out loud—it analyzes the text, generates a conversational script between two distinct AI personalities, and lets you interrupt them to ask questions in real-time. 

**[Try the Live App Here]([https://auracast.onrender.com])**

---

## 💡 What can it do?

* 📚 **Bring Your Own Books:** You can upload any `.epub` or `.pdf`. The backend automatically parses the text and breaks it down by chapter so it doesn't overwhelm the AI's token limits.
* 🎭 **Two Distinct Hosts:** I used the **Gemini 1.5 Pro API** to act as the "director." It writes a dynamic script for two hosts—one who is warm and curious, and another who is logical and analytical.
* 🗣️ **Lifelike Audio:** The script gets passed to **Edge-TTS** (Microsoft's neural text-to-speech) to generate high-quality, distinct voices for the hosts. I used `pydub` to stitch all the audio clips together into one seamless track.
* ✋ **Interrupt & Ask:** This is my favorite feature! While listening, you can pause the audio, type a question about what they just said, and the hosts will generate a custom response and speak it right back to you.
* 🎨 **Glassmorphism UI:** I designed a custom, responsive frontend with audio speed controls, `.mp3` downloads, and a smooth Dark/Light mode toggle.
* 🛡️ **Demo Mode:** Since AI APIs have rate limits, I engineered a deterministic "Mock Mode" fallback so I can reliably demo the application without worrying about API timeouts.

---

## 🛠️ How it's built

**The Frontend:**
* HTML5, CSS3, and Vanilla JavaScript. (No heavy frameworks, just clean state management and DOM manipulation for the audio player and chat bubbles).

**The Backend:**
* **Python & Flask:** The core server handling file uploads and API routing.
* **Google Gemini 1.5 Pro (`google-generativeai`):** The brain behind the scriptwriting and literary analysis.
* **Microsoft Edge-TTS (`edge-tts`):** The vocal cords. 
* **Audio Processing:** `pydub` for audio concatenation.
* **Document Parsing:** `PyPDF2`, `ebooklib`, and `beautifulsoup4` to clean up the raw text.

**Deployment:**
* Hosted on Render using a `gunicorn` WSGI server.

---

## 🚀 Want to run it locally?

If you want to clone this repo and play with the code yourself, here is how to get it running:

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/YOUR_GITHUB_USERNAME/AuraCast.git](https://github.com/YOUR_GITHUB_USERNAME/AuraCast.git)
   cd AuraCast
