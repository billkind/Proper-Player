import React, { useState } from 'react';
import './App.css';
import VideoPreview from './VideoPreview';

function App() {
  const [file, setFile] = useState(null);
  const [logs, setLogs] = useState('');
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState(null);
  const [mode, setMode] = useState("mute");

  const handleFileChange = (e) => {
    setFile(e.target.files[0]);
    setResult(null);
    setLogs('');
    setProgress(0);
  };

  const handleUpload = async () => {
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    setLogs('⏳ Upload in progress...');
    setProgress(10);

    try {
      const response = await fetch('http://localhost:8000/analyze', {
        method: 'POST',
        body: formData,
      });
      const data = await response.json();
      setResult(data);
      setLogs(JSON.stringify(data, null, 2));
      setProgress(100);
    } catch (err) {
      setLogs('❌ Erreur : ' + err.message);
    }
  };

  return (
    <div className="app-container">
      {/* Header */}
      <header className="header">
        <div className="header-content">
          
          <img src="public/Headphones with Prohibition Icon.png" alt="" class="img1" width={50}/>
          <span className="app-title">PROPER PLAYER</span>
        </div>
      </header>

      {/* Main Content */}
      <main className="main-content">
        {/* Hero Section */}
        <div className="hero-section">
          <h1 className="hero-title">
            ♫PLAY<br />SAFELY
          </h1>
          <p className="hero-subtitle">
            Enjoy an environment where listening becomes your ally. Play without offensive language.
          </p>
        </div>

        {/* Upload Section */}
        <div className="upload-card">
          <div>
            <input
              type="file"
              accept="audio/*,video/*"
              onChange={handleFileChange}
              className="file-input"
              id="file-input"
            />
            <label htmlFor="file-input" className="file-label">
              <svg width="20" height="20" fill="currentColor" viewBox="0 0 24 24">
                <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/>
              </svg>
              Choose a file
            </label>
            
            {file && (
              <div className="file-selected">
                <p>Selected file:</p>
                <p className="file-name">{file.name}</p>
              </div>
            )}
          </div>

          {/* Mode Selection */}
          <div className="mode-selection">
            <label className="mode-label">Censorship Mode</label>
            <div className="mode-options">
              <div className="mode-option">
                <input
                  type="radio"
                  name="mode"
                  value="mute"
                  checked={mode === "mute"}
                  onChange={() => setMode("mute")}
                  id="mute"
                />
                <label htmlFor="mute">
                  <svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M12,4L9.91,6.09L12,8.18M4.27,3L3,4.27L7.73,9H3V15H7L12,20V13.27L16.25,17.53C15.58,18.04 14.83,18.46 14,18.7V20.77C15.38,20.45 16.63,19.82 17.68,18.96L19.73,21L21,19.73L12,10.73M19,12C19,12.94 18.8,13.82 18.46,14.64L19.97,16.15C20.62,14.91 21,13.5 21,12C21,7.72 18,4.14 14,3.23V5.29C16.89,6.15 19,8.83 19,12M16.5,12C16.5,10.23 15.5,8.71 14,7.97V10.18L16.45,12.63C16.5,12.43 16.5,12.21 16.5,12Z"/>
                  </svg>
                  Mute
                </label>
              </div>
              <div className="mode-option">
                <input
                  type="radio"
                  name="mode"
                  value="bip"
                  checked={mode === "bip"}
                  onChange={() => setMode("bip")}
                  id="bip"
                />
                <label htmlFor="bip">
                  <svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M14,3.23V5.29C16.89,6.15 19,8.83 19,12C19,15.17 16.89,17.85 14,18.71V20.77C18,19.86 21,16.28 21,12C21,7.72 18,4.14 14,3.23M16.5,12C16.5,10.23 15.5,8.71 14,7.97V16.03C15.5,15.29 16.5,13.77 16.5,12M3,9V15H7L12,20V4L7,9H3Z"/>
                  </svg>
                  Beep
                </label>
              </div>
            </div>
          </div>

          <button onClick={handleUpload} className="analyze-button" disabled={!file}>
            <svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4z"/>
            </svg>
            Analyze & Censor
          </button>

          {progress > 0 && (
            <div className="progress-container">
              <div className="progress-info">
                <span>Processing...</span>
                <span>{progress}%</span>
              </div>
              <div className="progress-bar-container">
                <div className="progress-bar" style={{ width: `${progress}%` }}></div>
              </div>
            </div>
          )}
        </div>

        {/* Video Player */}
        {result && file && (
          <div className="video-container">
            <VideoPreview
              videoUrl={URL.createObjectURL(file)}
              toxicSegments={result.toxic_words}
              mode={mode}
            />
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
