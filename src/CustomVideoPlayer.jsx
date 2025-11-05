import React, { forwardRef, useEffect, useState } from 'react';

const CustomVideoPlayer = forwardRef(({ src, onTimeUpdate }, ref) => {
  const [dimensions, setDimensions] = useState({
    width: 640,
    height: 360
  });

  useEffect(() => {
    const updateDimensions = () => {
      const containerWidth = Math.min(window.innerWidth - 32, 640);
      const aspectRatio = 16 / 9;
      const calculatedHeight = containerWidth / aspectRatio;
      
      setDimensions({
        width: containerWidth,
        height: calculatedHeight
      });
    };

    updateDimensions();
    window.addEventListener('resize', updateDimensions);
    
    return () => window.removeEventListener('resize', updateDimensions);
  }, []);

  useEffect(() => {
    if (!ref?.current || !onTimeUpdate) return;
    const handleTimeUpdate = () => onTimeUpdate(ref.current.currentTime);
    const video = ref.current;
    video.addEventListener('timeupdate', handleTimeUpdate);
    return () => {
      video.removeEventListener('timeupdate', handleTimeUpdate);
    };
  }, [onTimeUpdate, ref]);

  return (
    <div style={{
      border: '7px solid #ffffffff',
      borderRadius: '10px',
      overflow: 'hidden',
      width: '100%',
      maxWidth: `${dimensions.width}px`,
      margin: '0 auto'
    }}>
      <video
        ref={ref}
        src={src}
        controls
        width="100%"
        height="auto"
        style={{ 
          backgroundColor: 'rgba(0, 0, 0, 0.93)', 
          outline: 'none',
          display: 'block'
        }}
      />
    </div>
  );
});

export default CustomVideoPlayer;
