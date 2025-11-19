
const CircularProgressBar = ({circleWidth, progress, placement}) =>{
    const strokeWidth = 7;
    const radius = (circleWidth - strokeWidth) / 2;
    const dashArray = radius * Math.PI * 2;
    const dashOffset = dashArray - (dashArray * progress) / 100;

    
    return(
        <>
            <svg 
                width={circleWidth} 
                height={circleWidth}
                viewBox={`0 0 ${circleWidth} ${circleWidth}`}
                className={placement} 
            >
                {/* circle background */}
            <circle
                cx={circleWidth / 2}            
                cy={circleWidth / 2}
                strokeWidth={strokeWidth}
                r={radius}
                className="fill-neutral-200 stroke-neutral-400 dark:fill-gray-400 dark:stroke-gray-600"           
            />
            {/* circle progress */}
            <circle
                cx={circleWidth / 2}            
                cy={circleWidth / 2}
                strokeWidth={strokeWidth}
                r={radius}
                className={`fill-none stroke-zuccini-600 `} 
                style={{
                   strokeDasharray: dashArray,
                   strokeDashoffset: dashOffset
                }}
                transform= {`rotate(90 ${circleWidth / 2} ${circleWidth / 2})`}
            />
            <text 
            x="50%"
            y="50%" 
            dy='0.3em' 
            textAnchor="middle"
            className="text-sm font-semibold"
            >{progress}%</text>


            </svg>
        </>
    );


}

export default CircularProgressBar;