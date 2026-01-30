# ISODROP 💎🛸

<p align="center">
  <img src="api\static\icon.png" width="200" alt="ISODROP Icon">
</p>

**ISODROP** is a premium, real-time local file sharing web application designed for seamless data transfer across devices on the same Wi-Fi network. Built with a stunning glassmorphism aesthetic and a focus on speed, it provides an "AirDrop-like" experience for any browser.

## ✨ Features

- **Instant Device Discovery**: Real-time presence tracking shows exactly who's connected in the **Discovery Hub**.
- **PWA Ready**: Fully installable on **Android (Chrome)**, **PC**, and **iOS (Safari)**. Use it like a native app with a custom home screen icon.
- **Robust File Sharing**: Share text, images, and documents instantly.
- **Copy-to-Clipboard**: Quick "Copy Hub URL" with fallback support for local networks.
- **Dynamic QR Codes**: Instant connection for mobile devices via QR scanning.
- **History Management**: Clear session history with a single tap.
- **Ultra-Responsive**: Fluid design that looks stunning on high-res monitors and mobile phones.

## 🛠 Tech Stack

- **Backend**: Python (Flask, Flask-SocketIO)
- **Frontend**: Vanilla HTML5, CSS3 (Advanced Glassmorphism), JavaScript (ES6+)
- **Communication**: WebSockets (via Socket.IO) for real-time synchronization.
- **PWA**: Service Workers & Web App Manifest.
- **Deployment**: Fully optimized for **Vercel** serverless environments.

## 🚀 Getting Started

### Local Setup

1. **Clone the repository**:
   ```bash
   git clone <your-repo-url>
   cd WIFI
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the app**:
   ```bash
   python app.py
   ```

4. **Access the Hub**:
   Open `http://localhost:5000` in your browser. Other devices on the same Wi-Fi can join using your local IP.

### Vercel Deployment

1. Install the Vercel CLI: `npm i -g vercel`
2. Run `vercel` in the project root.
3. Once deployed, link your GitHub repository for automatic deployments.

## 📱 PWA Installation

- **Android/Chrome**: Tap the three dots and select **"Install App"**.
- **iOS/Safari**: Tap the **Share** button and select **"Add to Home Screen"**.
- **Desktop/Chrome**: Look for the **Install icon** in the address bar.

---
*Created with ❤️ for seamless sharing.*


