//for imports
import {
faStarHalfStroke,
faCircleXmark,
faHouse,
faStar
} from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {use, useCallback, useEffect, useState} from 'react'
import AreaContForm from '../components/AreaContForm';
import SubContForm from '../components/SubContForm';

import { apiGet, apiGetBlob } from '../utils/api_utils';
import { adminHelper, canRate } from '../utils/auth_utils';
import ProgramCard from '../components/ProgramCard';
import { CardSkeleton } from '../components/Skeletons';
import DocViewer, { DocViewerRenderers } from "@cyntler/react-doc-viewer";
import "@cyntler/react-doc-viewer/dist/index.css";
import "../../index.css";
import { Navigate, useLocation } from 'react-router-dom';


const Accreditation = () => {
  const [expandedAreaIndex, setExpandedAreaIndex] = useState(null);
  const [area, setArea] = useState([]);
  
  const [programs, setPrograms] = useState([]);
  
  const [docs, setDocs] = useState([]);
  const [showPreview, setShowPreview] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [docViewerKey, setDocViewerKey] = useState(0); // Force re-render key

  const [selfRateMode, setSelfRateMode] = useState(false);   
  
  const [visible, setVisible] = useState("programs");

  
  const [selectedProgram, setSelectedProgram] = useState(null);
  const [selectedArea, setSelectedArea] = useState(null);
  const [selectedSubarea, setSelectedSubarea] = useState(null);

  const [programLoading, setProgramLoading] = useState(false);
  const [areaRatings, setAreaRatings] = useState({});
  const isAdmin = adminHelper()
  const canRatePermission = canRate()

  if (!canRatePermission) return <Navigate to="/Dashboard" replace />
  
  useEffect(() => {
    const fetchProgram = async () => {
      if (!canRatePermission) return
      setProgramLoading(true);

      try {
        // Use our centralized API utility - no manual token handling!
        const response = await apiGet('/api/program');
  
            if (response.success) {
              Array.isArray(response.data.programs) ? setPrograms(response.data.programs) : setPrograms([]);
            } else {
              console.error('Failed to fetch programs:', response.error);
              setPrograms([]); // Set empty array on error
            }
            
  
        } catch (err){
          console.error("Error occurred when fetching programs", err)
  
        } finally {
          setProgramLoading(false);
        }
      }
        fetchProgram()
      }, [isAdmin]);

    //Fetch areas from specific programs
      const fetchAreasForProgram = async (programCode) => {
        try {
          const response = await apiGet(`/api/accreditation?programCode=${encodeURIComponent(programCode)}`)
          Array.isArray(response.data) ? setArea(response.data) : setArea([]);
        } catch(err){
          console.log(err.response?.data || err.message);
          setArea([]);
        }
      }
      
  const refreshAreas = async (programCode) => {
    try {
      const response = await apiGet(`/api/accreditation?programCode=${encodeURIComponent(programCode)}`, 
      {withCredentials: true})
      Array.isArray(response.data) ? setArea(response.data) : setArea([]);
      console.log("Refreshing areas...")
    } catch(err) {
      console.error('Error refreshing areas:', err);
    }
  }

const handleFilePreview = useCallback(async (docName, docPath) => {
  try {
    console.log('Preview requested for:', docName, docPath);
    
    setIsLoading(true);
    setError(null);
    setDocs([]); // Clear previous documents
    setShowPreview(true); 

    const blob = await apiGetBlob(`/api/accreditation/preview/${encodeURIComponent(docName)}`);

    // Construct the full URL
    const fileURL = URL.createObjectURL(blob);

    // Helper function to determine file type from filename
    const getFileType = (fileName) => {
      const extension = fileName.split('.').pop()?.toLowerCase();
      const typeMap = {
        'pdf': 'pdf',
        'doc': 'doc',
        'docx': 'docx',
        'xls': 'xls',
        'xlsx': 'xlsx',
        'ppt': 'ppt',
        'pptx': 'pptx',
        'txt': 'txt',
        'csv': 'csv',
        'jpg': 'jpg',
        'jpeg': 'jpeg',
        'png': 'png',
        'gif': 'gif'
      };
      return typeMap[extension] || extension;
    };

    const newDocument = {
      uri: fileURL,
      fileName: docName,
      fileType: getFileType(docName)
    };

    // Delay to ensure proper state transitions
    setTimeout(() => {
      setDocs([newDocument]);
      setShowPreview(true);
      setDocViewerKey(prev => prev + 1);

      setTimeout(() => {
        setIsLoading(false);
      }, 500);
    }, 100);

    
  } catch(err){
    console.error('Preview error:', err);
    setError(`Failed to load document: ${err.message}`);
    setIsLoading(false);
    setShowPreview(false);
  } 
}, []);

  
const handleDropDown = (area) => {
  const currentExpandedIndex = expandedAreaIndex === area.areaID;
  setExpandedAreaIndex(currentExpandedIndex ? null : area.areaID);
  setShowPreview(false);
  setSelectedArea(currentExpandedIndex ? null : area);    
  
  if(currentExpandedIndex || (selectedArea && selectedArea.areaID !== area.areaID)){
    setSelectedSubarea(null);
  }
}

// Function to set the visible area to "areas" and set the selected program
const visibleArea = (program) => {
  setVisible("areas");
  setSelectedProgram(program);
  fetchAreasForProgram(program.programCode);

}

// Clear navigation route to programs
const backToPrograms = () => {
  setVisible("programs");
  setSelectedProgram(null);
  setSelectedArea(null);
  setSelectedSubarea(null);
  setShowPreview(false);
  setSelfRateMode(false);
}

const handleAreaBreadcrumbClick = () =>{
  setSelectedSubarea(null)
  setShowPreview(false);

  if(selectedArea && expandedAreaIndex === selectedArea.areaID){
    // Area is already expanded, just clear subarea
    return;
  }
  // If area is not expanded, expand it
  if(selectedArea){
    setExpandedAreaIndex(selectedArea.areaID)
  }
}
const handleSubareaSelect = (subarea) => {
  setSelectedSubarea(subarea);
}

    const fetchAreaRating = async (programCode, areaID) => {
    try {
      const res = await apiGet(`/api/accreditation/rate/subarea/${programCode}/${areaID}`);

      let total = 0;
      let count = 0;

      for (const sub of res.data) {
        if (sub.rating && sub.rating > 0) { // Only count subareas that have been rated
          total += sub.rating;
          count++;
        }
      }

      const areaAvg = count > 0 ? total / count : 0;
      
      // Store rating per area
      setAreaRatings(prev => ({
        ...prev,
        [areaID]: areaAvg
      }));        

    } catch (err) {
      console.error("Failed to fetch area rating:", err);
    }
  };

  const refreshAreaRating = useCallback(async (programCode, areaID) => {      
    await fetchAreaRating(programCode, areaID);
  }, []);

  // Add this to your SubContForm component's rating save function:
  const onSubareaRatingUpdate = useCallback(() => {
    if (selectedProgram && selectedArea) {
      setTimeout(() => {
        refreshAreaRating(selectedProgram.programCode, selectedArea.areaID);
      }, 1000); // Small delay to ensure backend is updated
    }
  }, [selectedProgram, selectedArea, refreshAreaRating]);

  const computeProgramRating = () => {
      const ratings = Object.values(areaRatings);
      if (ratings.length === 0) return 0;
      const sum = ratings.reduce((acc, r) => acc + r, 0);

      return sum / ratings.length;
  };

  useEffect(() => {
    if (!isAdmin) return
    if (selectedProgram && area.length > 0) {        
      setAreaRatings({}); // Clear existing ratings first
      
      // Calculate ratings for all areas
      area.forEach(a => {
        fetchAreaRating(selectedProgram.programCode, a.areaID);
      });
    }
  }, [selectedProgram, area, isAdmin]);
  
  //Navigate to program of pending document from dashboard
  const location = useLocation()
  const state = location.state
  useEffect(()=> {
    const navigateToProgram = async ()=> {
      const res = await apiGet('/api/program')
      const programs = res.data.programs
      const program = programs.find(p => p.programCode === state.programCode)
      setSelectedProgram(program)
      setVisible("areas")
      fetchAreasForProgram(program.programCode)
      console.log('selected program: ', selectedProgram)
    }
    navigateToProgram()
  }, [state])

  // Navigate to area of pending document from dashboard
  let pendingDocArea = []
  useEffect(()=> {
    const navigateToArea = async ()=> {
      const res = await apiGet('/api/area')
      const areas = res.data.area
      pendingDocArea = areas.find(a => a.areaName === state.areaName)
      setSelectedArea(pendingDocArea)
      console.log('selected pending doc area: ', pendingDocArea)
      setExpandedAreaIndex(pendingDocArea.areaID)
      console.log('expanded area:', expandedAreaIndex)
    }
    navigateToArea()
  }, [state])

  // Navigate to subarea of pending document from dashboard
  // useEffect(()=> {
  //   const navigateToSubarea = async ()=> {
  //     const res = await apiGet('/api/subarea')
  //     const subareas = res.data
  //     console.log('subareas: ', subareas)
  //     console.log('selected area for subarea: ', pendingDocArea)
  //     if(expandedAreaIndex === pendingDocArea.areaID) {
  //       const pendingDocSubarea = subareas.find(sa => sa.subareaName === state.subareaName && sa.areaID === pendingDocArea.areaID)
  //       console.log('pending doc subarea: ', pendingDocSubarea)
  //       setSelectedSubarea(pendingDocSubarea)
  //     } else {console.log('No expanded area')}
  //     console.log('Selected subarea from dash: ', selectedSubarea)
  //   }
  //   navigateToSubarea()
  // }, [state])
  // console.log('Selected subarea: ', selectedSubarea)
              
    return(
    <>
        <div className="relative flex flex-row justify-around border border-neutral-300 rounded-[20px] w-full min-h-[85%] shadow-md inset-shadow-sm inset-shadow-gray-400 p-3 bg-neutral-200 dark:bg-gray-900 dark:inset-shadow-zuccini-800">
          <div className='relative flex flex-col w-full p-3' >
            <div className='flex flex-row md:w-full scale-85 -ml-8 md:-ml-0 md:scale-100 gap-5 mb-5 mt-15 md:mt-0'>
                         
              <FontAwesomeIcon icon={faHouse}
               onClick={() => {backToPrograms()}}
               className={`${visible === "programs" 
                ? 'text-gray-500 inset-shadow-sm inset-shadow-gray-400 bg-gray-300 dark:inset-shadow-gray-800 dark:bg-gray-800/50 dark:text-gray-400' 
                : 'cursor-pointer text-gray-500 bg-gray-200 hover:text-zuccini-500 dark:hover:text-zuccini-500/70 shadow-md dark:inset-shadow-sm dark:inset-shadow-gray-400 dark:bg-gray-950/50'
            } p-4 text-xl transition-all duration-200 border border-neutral-300 rounded-xl dark:border-neutral-500 cursor-pointer`}
               />                                           
            
              {/* Breadcrumbs */}
              <div className=' w-[58%] md:w-full p-3 font-semibold bg-neutral-300/90 rounded-xl border-neutral-300 text-neutral-800 dark:text-white inset-shadow-sm inset-shadow-gray-400 dark:border-gray-900 dark:shadow-md dark:shadow-zuccini-900 dark:bg-gray-950/50'>
                <nav className="flex items-center overflow-hidden font-semibold text-gray-700 gap-x-2 text-md lg:text-lg dark:text-white">
                  
                  {/* Programs Breadcrumb */}
                  <span 
                    onClick={() => backToPrograms()} 
                    className="flex items-center flex-shrink-0 transition-all cursor-pointer duration-250 hover:text-zuccini-500"
                    title="Programs"
                  >
                    Programs
                  </span>
                  
                  {/* Program Name Breadcrumb */}
                  {selectedProgram && (
                    <>
                      <span className="flex-shrink-0 text-gray-400 dark:text-gray-500">/</span>
                      <span 
                        onClick={() => {
                          // Stay in areas view but clear area/subarea selections
                          setSelectedArea(null);
                          setSelectedSubarea(null);
                          setExpandedAreaIndex(null);
                          setShowPreview(false);
                        }}
                        className="flex items-center min-w-0 truncate transition-all duration-300 cursor-pointer hover:text-zuccini-500"
                        title={selectedProgram.programName}
                      >
                        <span className="truncate">
                          {selectedProgram.programName.length > 25 
                            ? `${selectedProgram.programName.substring(0, 25)}...` 
                            : selectedProgram.programName
                          }
                        </span>
                      </span>
                    </>
                  )}
                  
                  {/* Area Name Breadcrumb */}
                  {selectedArea && (
                    <>
                      <span className="flex-shrink-0 text-gray-400 dark:text-gray-500">/</span>
                      <span 
                        onClick={() => {        
                          setSelectedSubarea(null);
                          setShowPreview(false);            
                        }}
                        className="flex items-center min-w-0 truncate transition-all duration-300 cursor-pointer hover:text-zuccini-500"
                        title={selectedArea.areaName}
                      >
                        <span className="truncate">
                          {selectedArea.areaName.length > 20 
                            ? `${selectedArea.areaName.substring(0, 20)}...` 
                            : selectedArea.areaName
                          }
                        </span>
                      </span>
                    </>
                  )}
                  
                  {/* Subarea Name Breadcrumb */}
                  {selectedSubarea && (
                    <>
                      <span className="flex-shrink-0 text-gray-400 dark:text-gray-500">/</span>
                      <span 
                        className="flex items-center min-w-0 truncate transition-all duration-200 hover:text-zuccini-500 text-zuccini-600 dark:text-zuccini-400"
                        title={selectedSubarea.subareaName}
                      >
                        <span className="truncate">
                          {selectedSubarea.subareaName.length > 20 
                            ? `${selectedSubarea.subareaName.substring(0, 20)}...` 
                            : selectedSubarea.subareaName
                          }
                        </span>
                      </span>
                    </>
                  )}
                  
                </nav>
              </div>
              {visible === "areas" && (
              <button
                title='Self Rate'               
                onClick={() => setSelfRateMode(prev => !prev)}
                className={`${selfRateMode 
                ? 'text-gray-500 inset-shadow-sm inset-shadow-gray-400 bg-zuccini-300 dark:inset-shadow-gray-900 dark:bg-gray-800/50 dark:text-gray-400' 
                : 'cursor-pointer text-gray-500 bg-gray-200 hover:text-zuccini-500 dark:hover:text-zuccini-500/70 shadow-md dark:inset-shadow-sm dark:inset-shadow-gray-400 dark:bg-gray-950/50'
            } p-3 px-4 text-xl transition-all duration-200 border border-neutral-300 rounded-xl dark:border-neutral-500 cursor-pointer`}
              >                

              <FontAwesomeIcon icon={faStarHalfStroke} className="z-10" />
            </button>
            )}
                            
          </div>

          {/* Area Containers */}
          <div className="relative flex flex-row flex-1 gap-4">
              
              {/* Programs/Areas */}
              <div className={`flex flex-col transition-all duration-500 ${showPreview ? 'w-1/2' : 'w-full'}`}>
                
                {/* Program Cards Section */}
                <div className={`${visible == "programs" ? 'block' : 'hidden'} flex flex-wrap gap-4`}>
                  {programLoading ? (
                      <>
                        <CardSkeleton />
                        <CardSkeleton />
                        <CardSkeleton />                  
                      </>
                      ) : (
                      <>
                        {programs.map(program=> (
                          <ProgramCard 
                            program={program} 
                            key={program.programID} 
                            onClick={()=> visibleArea(program)} 
                            className="shadow-xl hover:border-zuccini-700"
                          />                      
                        ))} 
                      </>
                  )}
                </div>

                {/* Areas Section */}
                {selectedProgram && visible === "areas" && (
                  <div className="flex flex-col w-full overflow-auto">
                    <div className="w-full p-2 text-gray-700 rounded-xl">
                      {area.sort((a, b) => a.areaID - b.areaID)
                      .map((area) => (
                            <div key={area.areaID} className='flex flex-col'>
                              <AreaContForm
                                title={area.areaName} 
                                onClick={() => handleDropDown(area)}
                                onIconClick={() => handleDropDown(area)}
                                isExpanded={expandedAreaIndex === area.areaID}
                                selfRateMode={selfRateMode}        
                                areaID={area.areaID}    
                                programCode={selectedProgram.programCode}     
                                areaRating = {areaRatings[area.areaID] ?? 0}   
                                onSaveAreaRating={(programCode, areaID) => refreshAreaRating(programCode, areaID)}                                                         
                              /> 
                            
                              <div className={`list-upper-alpha list-inside overflow-hidden transition-all duration-500 ease-in-out ${expandedAreaIndex === area.areaID ? 'max-h-[2000px] opacity-100' : 'max-h-0 opacity-0'}`}>
                              {Array.isArray(area.subareas) && area.subareas.length > 0 ? (area.subareas.filter(sa => sa.subareaID != null).map((subarea) => (
                                <SubContForm 
                                  key={subarea.subareaID} 
                                  title={subarea.subareaName} 
                                  criteria={subarea.criteria} 
                                  onClick={() => {handleSubareaSelect(subarea)}}                                                               
                                  onRefresh={() => refreshAreas(selectedProgram.programCode)}
                                  onFilePreview={handleFilePreview}
                                  programCode = {selectedProgram.programCode} // passes program code
                                  selfRateMode = {selfRateMode} // passes the self rate mode
                                  subareaID={subarea.subareaID}                 
                                  onSubareaRatingUpdate={onSubareaRatingUpdate}                                              
                                  
                                />))
                                ) : (
                                <div className='flex flex-col items-center justify-center min-h-[150px] p-5 mb-3 text-neutral-800 bg-neutral-300/50 dark:bg-gray-800/50 dark:text-white rounded-2xl'>
                                  <h1 className='text-lg text-gray-500'>No Sub-Areas found</h1>                                    
                                </div>
                                )
                              }
                                {selfRateMode && (
                                  <div 
                                  className='flex flex-row items-center justify-end p-3 mb-2 ml-5 transition-all duration-300 border shadow-md cursor-pointer rounded-2xl border-neutral-400 text-neutral-800 dark:text-white dark:bg-gray-950/50 dark:border-gray-700 dark:hover:border-gray-600 inset-shadow-sm inset-shadow-gray-400 dark:shadow-md dark:shadow-zuccini-900 '>
                                    <h1 className='mr-3 text-xl italic font-semibold'>Overall Area Rating: </h1>
                                      <button                                        
                                        className={`relative flex flex-row items-center align-center p-3 px-15 mr-3 text-sm font-semibold overflow-hidden transition-all duration-300 text-gray-600 bg-gray-200 cursor-pointer rounded-3xl inset-shadow-sm inset-shadow-gray-400 dark:bg-gray-900 dark:text-gray-200`} >
                                        <FontAwesomeIcon icon={faStar} className='mr-3'/>        
                                        <h1 className='text-xl transition-all duration-300'>{(areaRatings[area.areaID] ?? 0 ).toFixed(1)}</h1> {/* Rating */}     
                                      </button>    
                                  </div>
                                )}  
                              </div>                                
                            </div>
                          ))}          
                            {selfRateMode && (
                                <div 
                                className='flex flex-row items-center justify-end min-w-full p-3 mb-2 transition-all duration-300 border shadow-md cursor-pointer border-neutral-400 rounded-2xl text-neutral-800 dark:text-white inset-shadow-sm inset-shadow-gray-400 dark:shadow-md dark:shadow-zuccini-900 dark:bg-gray-950/50 dark:border-gray-700 dark:hover:border-gray-600'>
                                  <h1 className='mr-3 text-xl font-semibold'>Overall Rating: </h1>
                                    <button                                        
                                      className={`relative flex flex-row items-center align-center p-3 px-15 mr-3 text-sm font-semibold overflow-hidden transition-all duration-300 text-gray-600 bg-gray-200 cursor-pointer rounded-3xl inset-shadow-sm inset-shadow-gray-400 dark:bg-gray-900 dark:text-gray-200`} >
                                      <FontAwesomeIcon icon={faStar} className='mr-3'/>        
                                      <h1 className='text-xl transition-all duration-300'>{computeProgramRating().toFixed(1)}</h1> {/* Rating */}     
                                    </button>    
                                </div>
                              )}  
                    </div>
                  </div>
                )}
                
              </div>

              {/* Document Viewer */}
              
              <div className={`sticky top-0 transition-all duration-500 ease-in-out overflow-hidden ${showPreview ? 'w-1/2 opacity-100' : 'w-0 opacity-0'}`} 
                    style={{ height: showPreview ? '95vh' : '0' }}>
                {showPreview && (
                  <div className='relative w-full h-full bg-white rounded-lg shadow-lg' style={{ minHeight: '100%', minWidth: '400px' }}>
                    
                    {/* Loading State */}
                    {isLoading && (
                      <div className="flex items-center justify-center h-full">
                        <div className="text-lg">Loading document...</div>
                      </div>
                    )}
                    
                    {/* Error State */}
                    {error && (
                      <div className="flex flex-col items-center justify-center h-full p-4">
                        <div className="mb-2 text-lg text-red-500">Error Loading Document</div>
                        <div className="text-sm text-center text-gray-600">{error}</div>
                        <button 
                          onClick={() => {setShowPreview(false); setError(null);}}
                          className="px-4 py-2 mt-4 text-white bg-blue-500 rounded hover:bg-blue-600"
                        >
                          Close
                        </button>
                      </div>
                    )}
                    
                    {/* Document Viewer */}
                    {!isLoading && !error && docs.length > 0 && (
                      <>
                        <div className="absolute inset-0 w-full h-full">
                          <DocViewer 
                            key={docViewerKey} // Force re-render when key changes
                            pluginRenderers={DocViewerRenderers}
                            documents={docs}    
                            className="doc-viewer"
                            prefetchMethod="GET"
                            config={{
                              header: {
                                disableHeader: false,
                                disableFileName: false,
                                retainURLParams: false,
                              },
                              pdfZoom: {
                                defaultZoom: 1.0,
                                zoomJump: 0.3,
                              },
                              pdfVerticalScrollByDefault: false,
                              loadingRenderer: {
                                showLoadingTimeout: false,
                              }
                            }}
                            style={{ 
                              height: '100%',
                              width: '100%',
                              position: 'absolute',
                              top: 0,
                              left: 0,
                              right: 0,
                              bottom: 0
                            }}
                          />
                        </div>

                        {/* Close Button */}
                        <FontAwesomeIcon 
                          icon={faCircleXmark} 
                          onClick={() => {
                            setShowPreview(false);
                            setDocs([]);
                            setError(null);
                          }}
                          className="absolute z-10 text-2xl transition-all duration-300 border-black rounded-full cursor-pointer text-white/50 border-1 top-3 right-4 hover:text-red-400"
                        /> 
                        
                        {/* View Full Document Button */}
                        <button 
                          onClick={() => {
                            if(docs.length > 0) {
                              window.open(docs[0].uri, '_blank');
                            }
                          }}
                          className="absolute z-10 px-4 py-2 font-medium text-white transition-all duration-300 bg-green-600 rounded-lg shadow-lg bottom-4 right-4 hover:bg-green-700"
                        >
                          View Full Document
                        </button>
                      </>
                    )}
                  </div>
                )}
              </div>

            </div>
          {showPreview && (
            <div className='relative w-full h-full' style={{ minHeight: '600px', minWidth: '400px' }}>
              
              {/* Loading State */}
              {isLoading && (
                <div className="flex items-center justify-center h-full">
                  <div className="text-lg">Loading document...</div>
                </div>
              )}
              
              {/* Error State */}
              {error && (
                <div className="flex flex-col items-center justify-center h-full p-4">
                  <div className="mb-2 text-lg text-red-500">Error Loading Document</div>
                  <div className="text-sm text-center text-gray-600">{error}</div>
                  <button 
                    onClick={() => {setShowPreview(false); setError(null);}}
                    className="px-4 py-2 mt-4 text-white bg-blue-500 rounded hover:bg-blue-600"
                  >
                    Close
                  </button>
                </div>
              )}                                
              
            </div>
          )}
        </div>
      </div>
    </>
    )
};

export default Accreditation;