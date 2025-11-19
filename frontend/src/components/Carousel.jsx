import Slider from "react-slick";
import "slick-carousel/slick/slick.css";
import "slick-carousel/slick/slick-theme.css";
//Importing Figures
import LoginFigure1 from '../assets/login-figure-1.svg';
import LoginFigure2 from '../assets/login-figure-2.svg';
import LoginFigure3 from '../assets/login-figure-3.svg';


 const Carousel = () =>{
  //slide contents
  const slides=[
    {
      figure: LoginFigure1,
      title: "University Document Management System",
      subTitle: "Centralized platform for secure, smart, and predictive accreditation workflows."
    },
    {
      figure: LoginFigure2,
      title: "Smart Document Management for Enhanced Accreditation",
      subTitle: "Access. Upload. Predict. Streamline your accreditation journey with our University Document Management System."
   
   
    },
    {
      figure: LoginFigure3,
      title: "Building Accreditation Success Together",
      subTitle: "A unified platform for program chairs and accreditors to work smarter, not harder."
    }
  ]

  //slider settings
  const settings = {
    dots: true,
    infinite: true,
    arrows: false,
    speed: 500,
    slidesToShow: 1,
    slidesToScroll: 1,
    autoplay: true,
    autoPlaySpeed: 5000
  };

  return (
      //carousel wrapper
     <div className="w-[80%] h-[85%] mt-14 ml-26 bg-transparent p-2 rounded-4xl"> 
         {/* slides container */}
        <div className=" px-2 h-full w-full text-center border-3 border-neutral-900  backdrop-blur-md shadow-2xl/60 rounded-3xl ">
         <Slider {...settings}>
               {slides.map((slide, index) =>{
                  return(
                     <div key={index} className="flex flex-col justify-center h-full">
                        <div className="flex flex-1 items-center justify-center">
                        <img src={slide.figure} className="h-full max-h-[400px] w-full object-contain"/>
                        </div>
                        {/* caption */}
                        <div>
                           <h1 className="text-emerald-300 text-3xl text-shadow-lg text-shadow-gray-900 font-semibold">{slide.title}</h1>
                           <h2 className="line-clamp-3 text-lg font-extralight">{slide.subTitle}</h2>
                        </div>
                     </div>)    
                     })
               }
         </Slider>
        </div>
     </div>

      
      
  
  );
 };



  
export default Carousel;