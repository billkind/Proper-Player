import React, { forwardRef, useEffect } from 'react';

const CustomVideoPlayer = forwardRef(({ src, onTimeUpdate, width = 640, height = 360 }, ref) => {
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
      width: `${width}px`
    }}>
      <video
        ref={ref}
        src={src}
        controls
        width={width}
        height={height}
        style={{ backgroundColor: 'rgba(0, 0, 0, 0.93)', outline: 'none' }}
      />
    </div>
  );
});

export default CustomVideoPlayer;
