import React, { useRef, useEffect, useState } from 'react';
import CustomVideoPlayer from './CustomVideoPlayer';

function VideoPreview({ videoUrl, toxicSegments = [], mode }) {
  const videoRef = useRef(null);
  const [isMutedSegment, setIsMutedSegment] = useState(false);
  const bipSound = new Audio("/bip.mp3");
  bipSound.volume = 1;

  const reducedVolume = 0;
  const normalVolume = 1.0;

  useEffect(() => {
    const interval = setInterval(() => {
      const video = videoRef.current;
      if (!video) return;

      const currentTime = video.currentTime;
      const matchedSegment = toxicSegments.find(
        (seg) => currentTime >= seg.start - 0.1 && currentTime <= seg.end + 0.06
      );

      if (matchedSegment) {
        if (mode === "mute") {
          video.muted = true;
        } else if (mode === "bip") {
          video.muted = false;
          video.volume = reducedVolume;
          bipSound.play().catch(() => {});
        }
        setIsMutedSegment(true);
      } else {
        video.muted = false;
        video.volume = normalVolume;
        setIsMutedSegment(false);
      }
    }, 200);

    return () => clearInterval(interval);
  }, [toxicSegments, mode]);

  const cardStyle = {
    background: 'rgba(255, 255, 255, 0.05)',
    backdropFilter: 'blur(10px)',
    border: '1px solid rgba(255, 255, 255, 0.1)',
    borderRadius: '1rem',
    padding: '1.5rem'
  };

  const badgeStyle = {
    position: 'absolute',
    top: '1rem',
    left: '1rem',
    background: 'rgba(239, 68, 68, 0.9)',
    color: 'white',
    padding: '0.5rem 0.75rem',
    borderRadius: '0.375rem',
    fontSize: '0.875rem',
    fontWeight: 'bold',
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    zIndex: 10
  };

  const alertStyle = {
    marginTop: '1.5rem',
    textAlign: 'center'
  };

  const alertHeaderStyle = {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '0.5rem',
    marginBottom: '1rem',
    color: '#ef4444'
  };

  const alertTextStyle = {
    color: 'rgba(255, 255, 255, 0.7)',
    fontSize: '1rem'
  };

  return (
    <div style={cardStyle}>
      <div style={{ position: 'relative' }}>
        <div style={{ display: 'flex', justifyContent: 'center' }}>
          <div style={{ position: 'relative', display: 'inline-block' }}>
            <CustomVideoPlayer
              ref={videoRef}
              src={videoUrl}
              onTimeUpdate={(currentTime) => {
                const matchedSegment = toxicSegments.find(
                  (seg) => currentTime >= seg.start - 0.1 && currentTime <= seg.end + 0.06
                );

                if (matchedSegment && videoRef.current) {
                  if (mode === "mute") {
                    videoRef.current.muted = true;
                  } else if (mode === "bip") {
                    videoRef.current.muted = false;
                    videoRef.current.volume = reducedVolume;
                    bipSound.play().catch(() => {});
                  }
                  setIsMutedSegment(true);
                } else if (videoRef.current) {
                  videoRef.current.muted = false;
                  videoRef.current.volume = normalVolume;
                  setIsMutedSegment(false);
                }
              }}
            />
            
            {isMutedSegment && (
              <div style={badgeStyle}>
                <svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12,4L9.91,6.09L12,8.18M4.27,3L3,4.27L7.73,9H3V15H7L12,20V13.27L16.25,17.53C15.58,18.04 14.83,18.46 14,18.7V20.77C15.38,20.45 16.63,19.82 17.68,18.96L19.73,21L21,19.73L12,10.73M19,12C19,12.94 18.8,13.82 18.46,14.64L19.97,16.15C20.62,14.91 21,13.5 21,12C21,7.72 18,4.14 14,3.23V5.29C16.89,6.15 19,8.83 19,12M16.5,12C16.5,10.23 15.5,8.71 14,7.97V10.18L16.45,12.63C16.5,12.43 16.5,12.21 16.5,12Z"/>
                </svg>
                CENSORED
              </div>
            )}
          </div>
        </div>

        {toxicSegments.length > 0 && (
          <div style={alertStyle}>
            <div style={alertHeaderStyle}>
              <svg width="20" height="20" fill="currentColor" viewBox="0 0 24 24">
                <path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/>
              </svg>
              <h4 style={{ margin: 0, fontSize: '1.125rem', fontWeight: '600' }}>
                Offensive Language Detected
              </h4>
            </div>
            <p style={alertTextStyle}>
              {toxicSegments.length} inappropriate segment{toxicSegments.length > 1 ? 's' : ''} found and will be {mode === 'mute' ? 'muted' : 'replaced with beep sounds'}.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

export default VideoPreview;
