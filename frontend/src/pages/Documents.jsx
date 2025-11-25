import {
  faMagnifyingGlass,
  faEllipsisVertical,
  faFilePdf, 
  faFileWord, 
  faFileImage, 
  faFileExcel, 
  faFilePowerpoint, 
  faFileLines,
  faFolder,
  faCircleInfo,
  faFolderOpen,
  faTrash,
  faArrowLeft,
  faDownload,
  faTriangleExclamation,
  faSpinner,
  faXmark,
  faPenToSquare,
  faPlus,
  faCircleNotch,
  faChevronDown,
  faChevronUp
} from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { useState, useRef, useEffect } from "react";
import { useLocation } from 'react-router-dom';
import { apiDelete, apiGet, apiPut, API_URL } from '../utils/api_utils';
import { DocumentSkeleton } from '../components/Skeletons';
import  StatusModal  from '../components/modals/StatusModal';
import  DocUpload  from '../components/modals/DocUpload';


const Documents = () => {

  const location = useLocation()

  const docRef = useRef(null);
  const collapsedMenuRef = useRef(null);    

  const [openIndex, setOpenIndex] = useState(null);    
  const [tags, setTags] = useState([]); // State to hold tags
  const [activeTags, setActiveTags] = useState([]) 
  const [showAllTags, setShowAllTags] = useState(false);
  const [viewMode, setViewMode] = useState("directory") // "directory" or "tag" 
  const [filteredDocs, setFilteredDocs] = useState([]);


  const [showDeleteModal, setShowDeleteModal] = useState(false);
  
  const [showStatusModal, setShowStatusModal] = useState(false); // shows the status modal
  const [statusMessage, setStatusMessage] = useState(null); // status message
  const [statusType, setStatusType] = useState("success"); // status type (success/error)
  
  const [isLoading, setIsLoading] = useState(false);
  
  const [directory, setDirectory] = useState(null);
  const [currentPath, setCurrentPath] = useState([]);

  const [showDetails, setShowDetails] = useState(false);

  const [selectedFile, setSelectedFile] = useState(null);

  const [showCollapsedMenu, setShowCollapsedMenu] = useState(false);

  const [renameTarget, setRenameTarget] = useState(null);
  const [renameValue, setRenameValue] = useState("");
  const [isRenaming, setIsRenaming] = useState(false);

  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [expandedFolders, setExpandedFolders] = useState([]);
  const [highlightedFile, setHighlightedFile] = useState(null);

  const [fileToDelete, setFileToDelete] = useState(null);

  const [showUploadModal, setShowUploadModal] = useState(false);

  const [loading, setLoading] = useState(false);

  // Handle navigation from search bar
  useEffect(() => { 
    if (location.state?.navigateToFile){
      const { currentPath: navPath, expandedFolders: navExpanded, highlightedFile: navHighlighted} = location.state.navigateToFile;

      setCurrentPath(navPath);
      setExpandedFolders (prev => Array.from(new Set([...prev, ...navExpanded])))
      setHighlightedFile(navHighlighted)

      window.history.replaceState({}, document.title);

      setQuery("");

      setTimeout(() => {
        setHighlightedFile(null)
      }, 3000);
    }
  }, [location.state])


  useEffect( () => {
          const handleOutsideClick = (e) => {
              if (docRef.current && !docRef.current.contains(e.target)){
                 setOpenIndex(null)
              }
          }
  
          document.addEventListener('mousedown', handleOutsideClick)
          return () => {
              document.removeEventListener('mousedown', handleOutsideClick)
          }
      },[openIndex])

  // Handle outside click for collapsed menu
  useEffect(() => {
    const handleOutsideClick = (e) => {
      if (collapsedMenuRef.current && !collapsedMenuRef.current.contains(e.target)) {
        setShowCollapsedMenu(false);
      }
    }

    document.addEventListener('mousedown', handleOutsideClick);
    return () => {
      document.removeEventListener('mousedown', handleOutsideClick);
    }
  }, [showCollapsedMenu])

  useEffect(() => {
    
  const fetchTags = async () => {
      try{
        const res = await apiGet('/api/documents/tags')

        setTags(Array.isArray(res.data) ? res.data : [])        
      } catch (err) {
        console.error("Failed to fetch tags", err)
        setTags([]);
      }
    } 
    fetchTags();
  }, [])


  useEffect(() => {
    const fetchDirectory = async () => {
      try{
        const res = await apiGet('/api/documents');
        setDirectory(res.data)
        console.log("Directories fetched...", res.data)
      } catch (err){
        console.error("An error occurred when fetching directories", err)
      }
 
    }
    fetchDirectory();
  }, []);


  const getCurrentFolder = () => {
    if (!directory ) return null;
    let folder = directory
    let validPath = []

    for (const part of currentPath){
      // Check if current folder has a folders property and the specific folder exists
    if (!folder.folders || !folder.folders[part]) {     

        setCurrentPath(validPath);
        return folder;
      }

      folder = folder.folders[part];
      validPath.push(part);
    }
    return folder;
  }
 
  const currentFolder = getCurrentFolder();

  // Utility for cleaning the paths
  const buildPath = (currentPath, fileName = "") => {
    // Join currentPath array and optional fileName into one clean string
    const path = [...currentPath, fileName].filter(Boolean).join("/");
    return encodeURIComponent(path); // Always encoded before sending to backend
  };
  
  const handleResultClick = (doc) => {
    let pathArray = doc.docPath.split('/').filter(Boolean);
    

    if(pathArray.length > 0 && pathArray[0] === "UDMS_Repository"){
      pathArray = pathArray.slice(1);
      console.log("Path removed udms: ", pathArray)
    }

    pathArray = pathArray.map(decodeURIComponent);

    let folderPath = directory;
    let filePath = []

    for (const pathPart of pathArray){
      if(folderPath?.folders?.[pathPart]){
        folderPath = folderPath.folders[pathPart]
        filePath.push(pathPart)
      } else{
         console.warn(`Path part '${pathPart}' not found. Using valid portion: [${filePath.join(', ')}]`);
      break;
      }
    }

    const folderPaths = filePath.map((_, i) => filePath.slice(0, i + 1).join('/')); 

    // Expand all folders
    setExpandedFolders (prev => Array.from(new Set([...prev, ...folderPaths])))
    
    // Navigate to result directory
    setCurrentPath(filePath);

    // Highligh search file
    setHighlightedFile(doc.docID);

    setQuery("")

    // clear highlighted file after 3s
    setTimeout(() => {
      setHighlightedFile(null)
    }, 3000);
  }

  const refreshDirectory = async () => {
    // Refresh directory
    const updatedRes = await apiGet('/api/documents');
    setDirectory(updatedRes.data);
  }  

  
  const goBack = () => {
    setCurrentPath((prev) => prev.slice(0, -1));
  }

  // Function to navigate to a specific breadcrumb level
  const navigateTo = (index) => {
    if (index === 0) {
      // Navigate to Home (root)
      setCurrentPath([]);
    } else {
      // Navigate to the specific path level
      setCurrentPath((prev) => prev.slice(0, index));
    }
  };


  const handlePreview = (file) => {
    const path = buildPath(currentPath, file.name);    
    window.open(`${API_URL}/api/documents/preview/${path}`, "_blank");
  }

  const handleDownload = (file) => {
    const path = buildPath(currentPath, file.name); 
    window.location.href = `${API_URL}/api/documents/download/${path}`;
  }

  const handleDelete = async (docID) => {
  setIsLoading(true);  
  try {
    const res = await apiDelete(`/api/documents/delete_file/${docID}`);
    console.log("Deleted: ", res.data)
    setShowStatusModal(true);
    setStatusMessage(res.data.message);
    setStatusType("success");
    setShowDeleteModal(false);
    
    setIsLoading(false);
    

    // Refresh document files
   const updatedRes = await apiGet('/api/documents');
   setDirectory(updatedRes.data);

  } catch (err) {
    setIsLoading(false);
    setShowStatusModal(true);
    setStatusMessage("Failed to delete file.");
    setStatusType("error");
    console.error("Error during deletion: ", err);
  }
};

  const getFileExtension = (filename) => {
    if(typeof filename !==  "string") return ""; 
    return filename.split('.').pop().toLowerCase();
  }   

  const displayFileIcon = (filename) => {    
    const ext = getFileExtension(filename)

    switch (ext) {
      case 'pdf':
         return faFilePdf;        
      case 'doc':
      case 'docx':
         return faFileWord;        
        // for jpg, jpeg, and png file
      case 'jpg':      
      case 'jpeg':              
      case 'png':
      case 'webp':
         return faFileImage;        
      case 'xlsx':         
      case 'xls':
         return faFileExcel;        
      case 'ppt':        
      case 'pptx':
         return faFilePowerpoint;        
      case 'txt':
         return faFileLines;
      default:
        return faFolder;
      
    }
  }

  const formatSize = (size) => {
    if (!size || isNaN(size)) return "0 KB";

    if (size >= 1024 * 1024 * 1024) {
      return (size / (1024 * 1024 * 1024)).toFixed(2) + " GB";
    } else if (size >= 1024 * 1024) {
      return (size / (1024 * 1024)).toFixed(2) + " MB";
    } else if (size >= 1024) {
      return (size / 1024).toFixed(2) + " KB";
    } else {
      return size + " B";
    }
  };

  const getFolderSize = (folder) => {
  if (!folder) return 0;

  let totalSize = 0;

  // Sum all file sizes
  if (folder.files && Array.isArray(folder.files)) {
    folder.files.forEach((file) => {
      if (file.type === "file" && file.size) {
        totalSize += Number(file.size);
      }
    });
  }

  // Add the sizes of subfolders
  if (folder.folders && typeof folder.folders === "object") {
    Object.values(folder.folders).forEach((subfolder) => {
      totalSize += getFolderSize(subfolder);
    });
  }

  return totalSize;
};

const BASE_PATH = "UDMS_Repository/Accreditation";

const handleRename = async (target) => {
  if (!renameValue.trim() || renameValue === target.name) {
    setRenameTarget(null);
    setRenameValue("");
    return;
  }
  console.log(currentPath)
  setIsRenaming(true);

  const relativeOldPath = buildPath(currentPath, target.name);
  const relativeNewPath = buildPath(currentPath, renameValue.trim());

  const oldPath = `${BASE_PATH}/${relativeOldPath}`;
  const newPath = `${BASE_PATH}/${relativeNewPath}`;

  try {
    await apiPut("/api/documents/rename", { oldPath, newPath });
    await refreshDirectory();

  } catch (err) {
    console.error("Rename failed:", err.response?.data || err.message);
  }

  setRenameTarget(null);
  setRenameValue("");
  setIsRenaming(false);
};


useEffect(() => {
  // Don't call API if query is empty
  if (!query.trim()) {
    setResults([]);
    return;
  }
  setLoading(true)
  const delayDebounce = setTimeout(async () => {
    try {
      const res = await apiGet(`/api/search?q=${encodeURIComponent(query)}`);

      Array.isArray(res.data) ? setResults(res.data) : setResults([]);
      console.log(res.data); // should log Array(2)
    } catch (err) {
      console.error("Search failed:", err);
    } finally{
      setLoading(false)
    }
  }, 300); // 300ms debounce

  return () => clearTimeout(delayDebounce);
}, [query]);


  const handleSearch = async (e) => {
    e.preventDefault();
    if(!query.trim()) return;
    try{
        const res = await apiGet(`/api/search?q=${encodeURIComponent(query)}`);      

        Array.isArray(res.data) ? setResults(res.data) : setResults([]);
        console.log(res.data); 
      } catch(err){
        console.error("Search failed: ", err)
      }
  }

  const handleRemoveTag = (tag) => {
    setActiveTags((prev) => {
      if (prev.includes(tag)){
        return prev.filter((t) => t !== tag);
      } else {
        return [...prev, tag];
      }
    })
    setViewMode("directory")
  }



  
  
  
  const filterDocByTag = async (tag) => {
    try{
      const res = await apiGet(`/api/documents/filter?tag=${encodeURIComponent(tag)}`)
      console.log("Filtered docs structure:", res.data);
      setFilteredDocs(res.data);
      setActiveTags([tag]);
      setViewMode("tag");
    } catch (err) {
      console.error("Error filtering documents", err)
    }

  }
  
  // Function to clear all tags when ✕ button is clicked
  const handleClearTags = () => {
    setActiveTags([]); // Removes all active tags
    setShowAllTags(false);
    setViewMode("directory");
  };

  const tagsLimit = 10;

  const displayedTags = showAllTags ? tags : tags.slice(0, tagsLimit);
  const hasMoreTags = tags.length > tagsLimit;

  return (
    <>
        {showStatusModal && (
          <StatusModal message={statusMessage} type={statusType} showModal={showStatusModal} onClick={()=>setShowStatusModal(false)} />
        )}
        {showUploadModal && (
           <DocUpload
              showModal={showUploadModal}
              onClose={() => setShowUploadModal(false)}
              currentPath={currentPath}               
              uploadSuccess={refreshDirectory}
      />
        )} 
      
     

      {/* Outer container for the document panel */}
      <div className="relative flex flex-col justify-center border border-neutral-300 rounded-[20px] min-w-[950px] min-h-[90%] shadow-md inset-shadow-sm inset-shadow-gray-400 p-3 bg-neutral-200 dark:bg-gray-900 dark:inset-shadow-zuccini-800">     

           {/* Upload button */}
          <button
            onClick={() => setShowUploadModal(true)}
            className='fixed z-100 p-4 text-gray-700 transition-all duration-300 border shadow-xl cursor-pointer right-10 bottom-8 px-7 rounded-xl dark:bg-gray-950/50 hover:shadow-sm hover:shadow-zuccini-700'>
            <FontAwesomeIcon icon={faPlus} className="text-xl dark:text-gray-200" />
          </button>   
        
         {/* Search Bar Section */}        
        <div className="relative flex items-center w-full max-w-2xl my-4 place-self-center">
          <label className="mr-2 text-lg font-semibold text-shadow-2xs text-neutral-800 dark:text-white">Search</label>
          {/* Input field for typing search query */}
          <input
            type="text"
            placeholder="Type to search document..."
            className={`flex-grow px-3 py-2 text-base transition duration-300 bg-neutral-300/90 rounded-l-xl border-neutral-300 text-neutral-800 dark:text-white inset-shadow-sm inset-shadow-gray-400 outline-none dark:border-gray-900 dark:shadow-md dark:shadow-zuccini-900 dark:bg-gray-950/50`}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSearch(); // trigger search on Enter key
            }}
          />

          {/* Button to trigger search when clicked */}
          <button 
            className={`px-6 w-[45px] h-[42px] flex items-center justify-center border rounded-r-xl cursor-pointer border-neutral-300 text-neutral-800 dark:text-white inset-shadow-sm inset-shadow-gray-400 dark:border-gray-900 dark:shadow-md dark:shadow-zuccini-900 dark:bg-gray-950/50 bg-zuccini-600 hover:bg-zuccini-500 transition-all duration-500`}
            onClick={handleSearch}
          >
            <FontAwesomeIcon icon={faMagnifyingGlass} className="text-lg text-white" />
          </button>

              {/* Search results */}
            {query.trim() !== "" && (
              <ul className="absolute z-10 w-full max-w-[565px] p-2 pt-3 overflow-y-auto border border-gray-300 right-12 top-full bg-gray-200/10 backdrop-blur-sm rounded-b-xl text-neutral-800 dark:text-white dark:border-gray-900 dark:bg-gray-800/20 max-h-72 ">
                {loading ? (
                  <li className="flex justify-center p-3">
                    <FontAwesomeIcon icon={faCircleNotch} className="animate-spin text-zuccini-700" />
                  </li>
                ) : results.length > 0 ? (
                  results.map((doc) => (
                    <li
                      onClick={() => handleResultClick(doc)}
                      key={doc.docID}
                      className="p-2 mb-1 cursor-pointer rounded-xl hover:bg-gray-400/20 dark:hover:bg-gray-700/20"
                    >
                      <div className="flex flex-col">
                        <h1 className="text-lg font-medium">{doc.docName}</h1>
                        <span
                          className="text-sm italic text-gray-500 truncate"
                          dangerouslySetInnerHTML={{ __html: doc.file_snippet }}
                        />
                      </div>
                    </li>
                  ))
                ) : (
                  <li className="p-2 mb-1 cursor-pointer rounded-xl hover:bg-gray-400/20 dark:hover:bg-gray-700/20">
                    No results found
                  </li>
                )}
              </ul>
            )}
        </div>
 
        

        <div className='flex flex-row justify-around'>
        {/* Main content area */}
        <div className={`flex flex-col flex-1 transition-all duration-300 ${showDetails ? 'mr-2' : ''}`}>      
          
          {/* Filter Tags Section */}
           <div className="border border-neutral-300 dark:border-neutral-600 rounded-[20px] px-5 py-4 dark:bg-gray-950/50 inset-shadow-sm inset-shadow-gray-400 mb-2">

            {/* Header + removable tag chip (inline using flex) */}
            <div className="flex flex-wrap items-center gap-3 mb-3">
              <p className="text-sm font-medium text-neutral-800 dark:text-white">Filter by:</p>

              {activeTags.length > 0 && activeTags?.map((tag, index) => (
                <div
                  key={index}
                  className="inline-flex items-center px-4 py-1 text-sm text-gray-700 capitalize border rounded-full border-neutral-400 dark:text-white"
                >
                  {tag}
                  <button
                    className="ml-3 text-sm text-gray-500 cursor-pointer hover:text-red-600"
                    onClick={() => handleRemoveTag(tag)}
                  >
                    ✕
                  </button>
                </div>
              ))}
              {activeTags.length > 0 && (
                <button
                  className="px-3 py-1 ml-3 text-xs text-gray-600 border border-gray-400 rounded-full hover:text-red-600"
                  onClick={handleClearTags}
                >
                  Clear All
                </button>
              )}
            </div>

            {/* Filter tags buttons */}
            <div className="flex flex-wrap items-center gap-2">
              {displayedTags.map((tag) => (
                <div
                  key={tag}
                  onClick={() => filterDocByTag(tag)}
                  className={`px-4 py-1 text-sm capitalize border rounded-full cursor-pointer transition-all duration-200
                    ${activeTags.includes(tag)
                      ? "inset-shadow-sm inset-shadow-gray-400 bg-gray-300 text-emerald-700 dark:bg-emerald-800 dark:text-gray-300"
                      : "shadow-md dark:shadow-sm dark:shadow-emerald-900 text-neutral-800 dark:text-white"
                    } border-neutral-300 dark:border-gray-700 hover:bg-neutral-300 dark:hover:bg-emerald-800`}
                >
                  {tag}
                </div>
              ))}

              {hasMoreTags && (
                <button
                  onClick={() => setShowAllTags(!showAllTags)}
                  className={`px-4 py-1 text-sm capitalize border rounded-full cursor-pointer transition-all duration-200 flex items-center gap-1
                    ${showAllTags
                      ? "inset-shadow-sm inset-shadow-gray-400 bg-gray-300 text-emerald-700 dark:bg-emerald-800 dark:text-gray-300"
                      : "shadow-md dark:shadow-sm dark:shadow-emerald-900 text-neutral-800 dark:text-white hover:bg-neutral-300 dark:hover:bg-emerald-800"
                    } border-neutral-300 dark:border-gray-700`}
                >
                  {showAllTags ? (
                    <>
                      Show less
                      <FontAwesomeIcon icon={faChevronUp} className="text-16 " />
                    </>
                  ) : (
                    <>
                      +{tags.length - tagsLimit} more
                      <FontAwesomeIcon icon={faChevronDown} className="text-16 " />
                    </>
                  )}
                </button>
              )}
            </div>
          </div>

          {/* BreadCrumbs */}
          <div className='flex flex-row gap-2'>
            <FontAwesomeIcon icon={faArrowLeft} 
              onClick={goBack}
              disabled={currentPath.length === 0}
             className={`${currentPath.length === 0 
                ? 'text-gray-500 inset-shadow-sm inset-shadow-gray-400 bg-gray-300 dark:inset-shadow-gray-800 dark:bg-gray-800/50 dark:text-gray-400' 
                : 'cursor-pointer text-gray-500 bg-gray-200 hover:text-zuccini-500 dark:hover:text-zuccini-500/70 shadow-md dark:inset-shadow-sm dark:inset-shadow-gray-400 dark:bg-gray-950/50'
            } p-4 text-xl transition-all duration-200 border border-neutral-300 rounded-xl dark:border-neutral-500`} />
             
            <div className='w-full p-3 font-semibold bg-neutral-300/90 rounded-xl border-neutral-300 text-neutral-800 dark:text-white inset-shadow-sm inset-shadow-gray-400 dark:border-gray-900 dark:shadow-md dark:shadow-zuccini-900 dark:bg-gray-950/50'>          
              <nav className="flex items-center font-semibold text-gray-700 gap-x-2 text-md lg:text-lg dark:text-white">
                {/* Home link */}
                <span 
                  className="flex items-center flex-shrink-0 transition-all cursor-pointer duration-250 hover:text-zuccini-500"
                  onClick={() => navigateTo(0)}
                  title="Home"
                >
                  Home
                </span>
                
                {/* Breadcrumb path items */}
                {currentPath.length > 0 && (
                  <>
                    {/* Show collapsed breadcrumb if path is long */}
                    {currentPath.length > 4 ? (
                      <>
                        {/* Show first 2 folders */}
                        {currentPath.slice(0, 2).map((pathPart, index) => (
                          <span key={index} className="flex items-center min-w-0 gap-x-2">
                            <span className="flex-shrink-0 text-gray-500">/</span>
                            <span 
                              className="flex items-center transition-all cursor-pointer duration-250 hover:text-zuccini-500 "
                              onClick={() => navigateTo(index + 1)}
                              title={pathPart}
                            >
                              {pathPart}
                            </span>
                          </span>
                        ))}
                        
                        {/* Collapse indicator with dropdown */}
                        <span className="flex-shrink-0 text-gray-500">/</span>
                        <div className="relative">
                          <button
                            onClick={() => setShowCollapsedMenu(!showCollapsedMenu)}
                            className="flex items-center px-2 py-1 text-sm transition-all rounded cursor-pointer duration-250 bg-gray-400/30 hover:bg-gray-400/50 dark:bg-gray-600/30 dark:hover:bg-gray-600/50"
                            title={`Click to show ${currentPath.length - 3} hidden folders`}
                          >
                            ...
                          </button>
                          
                          {/* Dropdown menu for collapsed folders */}
                          {showCollapsedMenu && (
                            <div
                              ref={collapsedMenuRef}
                              className="absolute top-full left-0 mt-1 z-50 bg-gray-200 dark:bg-gray-800 border border-gray-400 dark:border-gray-600 rounded-lg shadow-lg py-2 min-w-[200px] max-w-[300px]"
                            >
                              {currentPath.slice(2, -1).map((pathPart, index) => (
                                <button
                                  key={index}
                                  onClick={() => {
                                    navigateTo(index + 3); // +3 because we're starting from index 2
                                    setShowCollapsedMenu(false);
                                  }}
                                  className="block w-full px-4 py-2 text-sm text-left text-gray-700 truncate transition-colors dark:text-gray-200 hover:bg-gray-300 dark:hover:bg-gray-700"
                                  title={pathPart}
                                >
                                  <span className="mr-2 text-gray-400">📁</span>
                                  {pathPart}
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                        
                        {/* Show last folder */}
                        <span className="flex-shrink-0 text-gray-500">/</span>
                        <span 
                          className="flex items-center transition-all cursor-pointer duration-250 hover:text-zuccini-500"
                          onClick={() => navigateTo(currentPath.length)}
                          title={currentPath[currentPath.length - 1]}
                        >
                          {currentPath[currentPath.length - 1]}
                        </span>
                      </>
                    ) : (
                      /* Show full breadcrumb for shorter paths */
                      currentPath.map((pathPart, index) => (
                        <span key={index} className="flex items-center min-w-0 gap-x-2"> 
                          <span className="flex-shrink-0 text-gray-500">/</span>
                          <span 
                            className="flex items-center transition-all cursor-pointer duration-250 hover:text-zuccini-500"
                            onClick={() => navigateTo(index + 1)}
                            title={pathPart}
                          >
                            {pathPart}
                          </span>
                        </span>
                      ))
                    )}
                  </>
                )}
              </nav>
            </div>
          </div>

          {/* Grid for displaying file directory */}
          {viewMode === "directory" && (
            <div className="grid w-full gap-4 mt-6 md:grid-cols-2 sm:grid-cols-1 lg:grid-cols-3 ">                      
              {/* Folder Components */}          
              {currentFolder?.folders ? Object.keys(currentFolder.folders).map((folder) => {                
                return(
                  <div
                    key={folder}
                    onClick={() => {
                      setShowDetails(false);
                      setCurrentPath([...currentPath, folder])
                    }}
                    className="relative border text-neutral-800 border-neutral-400 dark:border-neutral-700 shadow-md rounded-[20px] px-4 py-5 flex justify-between items-center cursor-pointer hover:shadow-lg dark:hover:shadow-md dark:hover:shadow-zuccini-800 transition dark:bg-gray-950/50 dark:inset-shadow-sm dark:inset-shadow-gray-400">
                    
                    <div className="flex items-center space-x-3">
                      {/* Icon for Folder */}
                      <FontAwesomeIcon icon={displayFileIcon(folder)} className="text-3xl text-blue-400 cursor-pointer dark:text-blue-500" />

                      {/* Filename */}
                      {renameTarget === folder ? (
                          isRenaming ? (
                            // Show loading state
                            <div className="flex items-center">
                              <span className="font-medium text-gray-400 text-md dark:text-gray-400">
                                {renameValue}
                              </span>
                              <FontAwesomeIcon icon={faCircleNotch} className="ml-2 text-lg text-gray-400 animate-spin"/>
                            </div>
                          ) : (
                            // Rename mode
                            <input 
                              type='text'
                              value={renameValue}
                              onChange={(e) => setRenameValue(e.target.value)}
                              onClick={(e) => e.stopPropagation()}
                              onBlur={() => !isRenaming && handleRename({ name: folder, type: "folder" })}
                              onKeyDown={(e) => {
                                if (e.key === "Enter" && !isRenaming) {
                                  e.preventDefault();
                                  handleRename({ name: folder, type: "folder" });
                                }
                                if (e.key === "Escape") {
                                  setRenameTarget(null);
                                  setRenameValue("");
                                }
                              }}
                              className='px-2 py-1 bg-white border rounded outline-none'
                              autoFocus
                              disabled={isRenaming}
                            />
                          )
                        ) : (                        
                          <span className="font-medium whitespace-normal cursor-pointer text-md text-neutral-800 dark:text-white">
                            {folder.split(/(_|-)/g).map((part, i) => (
                              (part === '_' || part === '-') 
                                ? <span key={i}>{part}<wbr/></span>
                                : <span key={i}>{part}</span>
                            ))}
                          </span>
                        )}
                      
                    </div>
                    

                    {/* Menu icon (⋮) */}
                    <button                
                    onClick={(e) => {
                      e.stopPropagation();
                      setOpenIndex(openIndex === folder ? null : folder)
                    }}
                    className='p-2 transition-all duration-300 rounded-full'>
                    <FontAwesomeIcon icon={faEllipsisVertical}               
                    onClick={(e) => {
                      e.stopPropagation();
                      setOpenIndex(openIndex === folder ? null : folder)
                    }}
                    className="text-xl text-gray-500 cursor-pointer hover:text-black" />
                    </button>
                    {openIndex === folder && (
                      <div 
                      ref={docRef}
                      onClick={(e) => e.stopPropagation()}
                      className='absolute z-10 p-3 border shadow-xl bg-gray-200/10 backdrop-blur-sm rounded-xl w-35 -top-23 right-3 dark:bg-gray-900 '>
                        <button 
                        onClick={(e) => {
                          e.stopPropagation(); 
                          setRenameTarget(folder);
                          setRenameValue(folder);
                          setOpenIndex(null);
                        }}
                        className='relative block w-full px-2 py-1 text-gray-600 transition-all duration-300 rounded-md hover:text-gray-100 hover:bg-zuccini-500/80 dark:text-gray-200'>
                          Rename
                          <FontAwesomeIcon icon={faPenToSquare}  className="ml-5"/>
                        </button>
                        <div className="w-full my-2 border-b border-gray-600"/>
                        <button 
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedFile(currentFolder.folders[folder]);
                          console.log(selectedFile)
                          setShowDetails(true);
                          setOpenIndex(null);
                        }}
                        className='relative block w-full px-2 py-1 text-gray-600 transition-all duration-300 rounded-md hover:text-gray-100 hover:bg-gray-400/80 dark:text-gray-200'>
                          Details
                          <FontAwesomeIcon icon={faCircleInfo} className="ml-5"/>
                        </button>
                        <div className="w-full my-2 border-b border-gray-600"/>
                        <button className='relative block w-full px-2 py-1 text-gray-600 transition-all duration-300 rounded-md hover:text-gray-100 hover:bg-red-500/80 dark:text-gray-200'>
                          Delete
                          <FontAwesomeIcon icon={faTrash} className="ml-5"/>
                        </button>
                      </div>
                    )}
                  </div>                                                
              ) }) : (            
                <>
                  <DocumentSkeleton />
                  <DocumentSkeleton />
                  <DocumentSkeleton />
                </>
              )} 
          


              {/* File Components */}
              {currentFolder?.files?.map((file, index) => (
                <div
                  key={index}                                
                  onClick={() => {
                    handlePreview(file);
                    setHighlightedFile(null);
                  }}
                  className={`${highlightedFile === file.docID ? 'scale-101 ring-2 ring-zuccini-400/50' : 'ring-0'} relative border text-neutral-800 border-neutral-400 shadow-md rounded-[20px] px-4 py-5 flex justify-between items-center cursor-pointer hover:shadow-lg dark:hover:shadow-md dark:hover:shadow-zuccini-800 transition dark:bg-gray-950/50 dark:inset-shadow-sm dark:inset-shadow-gray-800`}
                >
                  <div className="flex items-center space-x-3">
                    {/* Icon for File */}
                    <FontAwesomeIcon
                    icon={displayFileIcon(file.name)}
                     className="text-3xl text-red-500 cursor-pointer dark:text-red-500" />

                    {/* Filename */}
                    <div className='flex flex-col flex-1 min-w-0'>
                      
                        {renameTarget === file ? (
                          // Show input when renaming is active
                          isRenaming ? (
                            // Show loading state instead of input when API call is in progress
                            <div className="flex items-center">
                              <span className="font-medium text-gray-400 text-md dark:text-gray-400">
                                {renameValue}
                              </span>
                              <FontAwesomeIcon icon={faSpinner} className="ml-2 text-lg text-gray-400 animate-spin"/>
                            </div>
                          ) : (
                            // Show input when not loading
                            <input 
                              type='text'
                              value={renameValue}
                              onChange={(e) => setRenameValue(e.target.value)}
                              onClick={(e) => e.stopPropagation()}
                              onBlur={() => !isRenaming && handleRename(file)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter" && !isRenaming) {
                                  e.preventDefault();
                                  handleRename(file);
                                }
                                if (e.key === "Escape") {
                                  setRenameTarget(null);
                                  setRenameValue("");
                                }
                              }}
                              className='px-2 py-1 bg-white border rounded outline-none'
                              autoFocus
                              disabled={isRenaming}
                            />
                          )
                        ) : (
                          // Show normal filename when not renaming
                          <span className="font-medium whitespace-normal cursor-pointer text-md text-neutral-800 hover:underline dark:text-white">
                            {file.name.split(/(_|-)/g).map((part, i) => (
                              (part === '_' || part === '-') 
                                ? <span key={i}>{part}<wbr/></span>
                                : <span key={i}>{part}</span>
                            ))}
                          </span>
                        )}                      
                      <span className="text-sm font-medium cursor-pointer text-neutral-600 dark:text-gray-400">
                        {formatSize(file.size)}
                      </span>
                    </div>
                  </div>

                  {/* Menu icon (⋮) */}

                  <button                
                    onClick={(e) => {
                      e.stopPropagation();
                      setOpenIndex(openIndex === file ? null : file)
                  }}
                  className='p-2 transition-all duration-300 rounded-full'>
                  <FontAwesomeIcon icon={faEllipsisVertical}               
                    onClick={(e) => {
                      e.stopPropagation();                    
                      setOpenIndex(openIndex === file ? null : file)
                    }}
                  className="text-xl text-gray-500 cursor-pointer hover:text-black" />
                  </button>
                  {openIndex === file && (

                    <div 
                      ref={docRef}
                      onClick={(e) => e.stopPropagation()}
                    className='absolute z-10 p-3 border shadow-xl bg-gray-200/10 backdrop-blur-sm rounded-xl min-w-35 -top-[170%] right-3 dark:bg-gray-900 '>

                      <button 
                        onClick={(e) => {                       
                          e.stopPropagation();
                          handleDownload(file);
                          console.log(`Downloading file: ${currentPath.join('/')}/${file.name}`);
                          }
                        }
                      className='relative block w-full px-2 py-1 text-gray-600 transition-all duration-300 rounded-md hover:text-gray-100 hover:bg-zuccini-500/80 dark:text-gray-200'>
                        Download
                        <FontAwesomeIcon icon={faDownload} className="ml-5"/>
                      </button>

                       <div className="w-full my-2 border-b border-gray-600"/> {/* Line */}

                      <button                       
                      onClick={(e) => {
                        e.stopPropagation(); 
                        setRenameTarget(file);
                        setOpenIndex(null);
                        setRenameValue(file.name);
                      }}
                      className='relative block w-full px-2 py-1 text-gray-600 transition-all duration-300 rounded-md hover:text-gray-100 hover:bg-gray-400/80 dark:text-gray-200'>
                        Rename
                        <FontAwesomeIcon icon={faPenToSquare} className="ml-5"/>
                      </button>

                      <div className="w-full my-2 border-b border-gray-600"/> {/* Line */}
                      
                      <button 
                      onClick={(e) => {
                        e.stopPropagation(); 
                        setShowDetails(true);
                        setOpenIndex(null);
                        setSelectedFile(file);
                      }}
                      className='relative block w-full px-2 py-1 text-gray-600 transition-all duration-300 rounded-md hover:text-gray-100 hover:bg-gray-400/80 dark:text-gray-200'>
                        Details
                        <FontAwesomeIcon icon={faCircleInfo} className="ml-5"/>
                      </button>
                     
                      <div className="w-full my-2 border-b border-gray-600"/> {/* Line */}

                      <button 
                      onClick={(e) => {
                        e.stopPropagation();
                        setFileToDelete(file);
                        setShowDeleteModal(true);
                        console.log(fileToDelete);
                        setOpenIndex(null);
                      }}                                     
                      className='relative block w-full px-2 py-1 text-gray-600 transition-all duration-300 rounded-md hover:text-gray-100 hover:bg-red-500/80 dark:text-gray-200'>
                        Delete
                        <FontAwesomeIcon icon={faTrash} className="ml-5"/>
                      </button>
                    </div>                                  
                  )}

                    {/* Delete Modal */}
                  {showDeleteModal && (
                    <div
                    onClick={(e) => {
                      e.stopPropagation();                                            
                    }}
                    className="fixed inset-0 z-50 flex items-center justify-center transition-all duration-300 transform scale-100 bg-black/60 backdrop-blur-xs">
                      <div className={`flex flex-col justify-center items-center p-5 py-10 border border-gray-800 bg-gray-200 dark:bg-gray-900 rounded-xl shadow-xl max-w-xl w-full max-h-[90vh] overflow-y-auto inset-shadow-sm inset-shadow-gray-400 dark:shadow-md dark:shadow-zuccini-800 ${showDeleteModal ? 'fade-in' : 'fade-out'}`}>
                        <h1 className='mb-4 text-4xl font-bold text-red-500 text-shadow-md'>Delete File</h1>
                        <div className="flex items-center justify-center w-20 h-20 mx-auto mb-3 bg-red-100 rounded-full inset-shadow-sm inset-shadow-red-500 dark:bg-red-900/30">
                          <FontAwesomeIcon icon={faTriangleExclamation} className="text-3xl text-red-500 dark:text-red-400"/>
                        </div>
                        <div className='flex flex-col justify-center items-center w-[90%]'>
                          <h1 className='mb-1 text-2xl font-semibold text-gray-800 dark:text-gray-200'>Are you sure you want to delete this file?</h1>
                          <p className='mb-5 text-lg text-center text-gray-600 dark:text-gray-400'>This file could be involved in the accreditation process. Please proceed with caution</p>
                        </div>
                        <div className='flex flex-row justify-around w-full'>
                          <button
                          onClick={() =>  setShowDeleteModal(false)}
                          className={`px-10 py-3 font-medium transition-colors rounded-full bg-gray-300 dark:bg-gray-700 text-neutral-500 dark:text-gray-300 hover:text-gray-900 hover:bg-gray-400/50 dark:hover:bg-gray-600 dark:hover:text-gray-200 cursor-pointer`}>Cancel</button>
                          <button 
                          onClick={() => handleDelete(file.docID)}
                          className={`${isLoading ? 'cursor-not-allowed bg-gray-700' : 'bg-red-600/70 hover:bg-red-600/90 cursor-pointer'} px-8 py-3 rounded-full font-medium transition-colors flex items-center  text-white `}>
                            {isLoading && (
                              <FontAwesomeIcon icon={faSpinner} className="mr-2 text-gray-400 animate-spin"/>
                            )}
                            Delete File</button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>          
              ))}  
              
          </div>
          )}  


          {viewMode === "tag" && (
            <div className="grid w-full gap-4 mt-6 md:grid-cols-2 sm:grid-cols-1 lg:grid-cols-3 ">
              {filteredDocs.length === 0 ? (
                <p>No Documents Found</p>
              ) : (
                <>
                {filteredDocs.map((file, index) => (
                  <div
                  key={index}                                
                  onClick={() => {
                    handlePreview(file);
                    setHighlightedFile(null);
                  }}
                  className={`${highlightedFile === file.docID ? 'scale-101 ring-2 ring-zuccini-400/50' : 'ring-0'} relative border text-neutral-800 border-neutral-800 shadow-md rounded-[20px] px-4 py-5 flex justify-between items-center cursor-pointer hover:shadow-lg dark:hover:shadow-md dark:hover:shadow-zuccini-800 transition dark:bg-gray-950/50 dark:inset-shadow-sm dark:inset-shadow-gray-800`}
                >
                  <div className="flex items-center space-x-3">
                    {/* Icon for File */}
                    <FontAwesomeIcon
                    icon={displayFileIcon(file.docName)}
                     className="text-3xl text-red-500 cursor-pointer dark:text-red-500" />

                    {/* Filename */}
                    <div className='flex flex-col flex-1 min-w-0'>
                      
                        {renameTarget === file ? (
                          // Show input when renaming is active
                          isRenaming ? (
                            // Show loading state instead of input when API call is in progress
                            <div className="flex items-center">
                              <span className="font-medium text-gray-400 text-md dark:text-gray-400">
                                {renameValue}
                              </span>
                              <FontAwesomeIcon icon={faSpinner} className="ml-2 text-lg text-gray-400 animate-spin"/>
                            </div>
                          ) : (
                            // Show input when not loading
                            <input 
                              type='text'
                              value={renameValue}
                              onChange={(e) => setRenameValue(e.target.value)}
                              onClick={(e) => e.stopPropagation()}
                              onBlur={() => !isRenaming && handleRename(file)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter" && !isRenaming) {
                                  e.preventDefault();
                                  handleRename(file);
                                }
                                if (e.key === "Escape") {
                                  setRenameTarget(null);
                                  setRenameValue("");
                                }
                              }}
                              className='px-2 py-1 bg-white border rounded outline-none'
                              autoFocus
                              disabled={isRenaming}
                            />
                          )
                        ) : (
                          // Show normal filename when not renaming
                          <span className="font-medium whitespace-normal cursor-pointer text-md text-neutral-800 hover:underline dark:text-white">
                            {file?.docName?.split(/(_|-)/g).map((part, i) => (
                              (part === '_' || part === '-') 
                                ? <span key={i}>{part}<wbr/></span>
                                : <span key={i}>{part}</span>
                            ))}
                          </span>
                        )}                                            
                    </div>
                  </div>

                  {/* Menu icon (⋮) */}

                  <button                
                    onClick={(e) => {
                      e.stopPropagation();
                      setOpenIndex(openIndex === file ? null : file)
                  }}
                  className='p-2 transition-all duration-300 rounded-full'>
                  <FontAwesomeIcon icon={faEllipsisVertical}               
                    onClick={(e) => {
                      e.stopPropagation();                    
                      setOpenIndex(openIndex === file ? null : file)
                    }}
                  className="text-xl text-gray-500 cursor-pointer hover:text-black" />
                  </button>
                  {openIndex === file && (

                    <div 
                      ref={docRef}
                      onClick={(e) => e.stopPropagation()}
                    className='absolute z-10 p-3 border shadow-xl bg-gray-200/10 backdrop-blur-sm rounded-xl min-w-35 -top-[170%] right-3 dark:bg-gray-900 '>

                      <button 
                        onClick={(e) => {                       
                          e.stopPropagation();
                          handleDownload(file);
                          console.log(`Downloading file: ${currentPath.join('/')}/${file.docName}`);
                          }
                        }
                      className='relative block w-full px-2 py-1 text-gray-600 transition-all duration-300 rounded-md hover:text-gray-100 hover:bg-zuccini-500/80 dark:text-gray-200'>
                        Download
                        <FontAwesomeIcon icon={faDownload} className="ml-5"/>
                      </button>

                       <div className="w-full my-2 border-b border-gray-600"/> {/* Line */}

                      <button                       
                      onClick={(e) => {
                        e.stopPropagation(); 
                        setRenameTarget(file);
                        setOpenIndex(null);
                        setRenameValue(file.name);
                      }}
                      className='relative block w-full px-2 py-1 text-gray-600 transition-all duration-300 rounded-md hover:text-gray-100 hover:bg-gray-400/80 dark:text-gray-200'>
                        Rename
                        <FontAwesomeIcon icon={faPenToSquare} className="ml-5"/>
                      </button>

                      <div className="w-full my-2 border-b border-gray-600"/> {/* Line */}
                      
                      <button 
                      onClick={(e) => {
                        e.stopPropagation(); 
                        setShowDetails(true);
                        setOpenIndex(null);
                        setSelectedFile(file);
                      }}
                      className='relative block w-full px-2 py-1 text-gray-600 transition-all duration-300 rounded-md hover:text-gray-100 hover:bg-gray-400/80 dark:text-gray-200'>
                        Details
                        <FontAwesomeIcon icon={faCircleInfo} className="ml-5"/>
                      </button>
                     
                      <div className="w-full my-2 border-b border-gray-600"/> {/* Line */}

                      <button 
                      onClick={(e) => {
                        e.stopPropagation();
                        setFileToDelete(file);
                        setShowDeleteModal(true);
                        console.log(fileToDelete);
                        setOpenIndex(null);
                      }}                                     
                      className='relative block w-full px-2 py-1 text-gray-600 transition-all duration-300 rounded-md hover:text-gray-100 hover:bg-red-500/80 dark:text-gray-200'>
                        Delete
                        <FontAwesomeIcon icon={faTrash} className="ml-5"/>
                      </button>
                    </div>                                  
                  )}
                
                </div> 
                ))}
              </>
              )}    
           {/* Delete Modal */}
                  {showDeleteModal && (
                    <div
                    onClick={(e) => {
                      e.stopPropagation();                                            
                    }}
                    className="fixed inset-0 z-50 flex items-center justify-center transition-all duration-300 transform scale-100 bg-black/60 backdrop-blur-xs">
                      <div className={`flex flex-col justify-center items-center p-5 py-10 border border-gray-800 bg-gray-200 dark:bg-gray-900 rounded-xl shadow-xl max-w-xl w-full max-h-[90vh] overflow-y-auto inset-shadow-sm inset-shadow-gray-400 dark:shadow-md dark:shadow-zuccini-800 ${showDeleteModal ? 'fade-in' : 'fade-out'}`}>
                        <h1 className='mb-4 text-4xl font-bold text-red-500 text-shadow-md'>Delete File</h1>
                        <div className="flex items-center justify-center w-20 h-20 mx-auto mb-3 bg-red-100 rounded-full inset-shadow-sm inset-shadow-red-500 dark:bg-red-900/30">
                          <FontAwesomeIcon icon={faTriangleExclamation} className="text-3xl text-red-500 dark:text-red-400"/>
                        </div>
                        <div className='flex flex-col justify-center items-center w-[90%]'>
                          <h1 className='mb-1 text-2xl font-semibold text-gray-800 dark:text-gray-200'>Are you sure you want to delete this file?</h1>
                          <p className='mb-5 text-lg text-center text-gray-600 dark:text-gray-400'>This file could be involved in the accreditation process. Please proceed with caution</p>
                        </div>
                        <div className='flex flex-row justify-around w-full'>
                          <button
                          onClick={() =>  setShowDeleteModal(false)}
                          className={`px-10 py-3 font-medium transition-colors rounded-full bg-gray-300 dark:bg-gray-700 text-neutral-500 dark:text-gray-300 hover:text-gray-900 hover:bg-gray-400/50 dark:hover:bg-gray-600 dark:hover:text-gray-200 cursor-pointer`}>Cancel</button>
                          <button 
                          onClick={() => handleDelete(file.docID)}
                          className={`${isLoading ? 'cursor-not-allowed bg-gray-700' : 'bg-red-600/70 hover:bg-red-600/90 cursor-pointer'} px-8 py-3 rounded-full font-medium transition-colors flex items-center  text-white `}>
                            {isLoading && (
                              <FontAwesomeIcon icon={faSpinner} className="mr-2 text-gray-400 animate-spin"/>
                            )}
                            Delete File</button>
                        </div>
                      </div>
                    </div>
                  )}
            </div>
          )}

        </div>

         
        
        {/* Details Panel */}          
        <div className={`flex flex-col h-fit min-h-[500px] z-0 shadow-xl bg-gradient-to-br from-gray-300 via-transparent to-gray-300 dark:from-gray-900  dark:to-gray-900 backdrop-blur-sm border border-gray-600 rounded-2xl p-3 dark:bg-gray-800 transition-all duration-300 ${showDetails ? 'opacity-100 w-80 fade-in-right' : 'opacity-0 w-0 fade-out-right'}`}>
          <div className="flex items-center justify-between mb-3">
            <h1 className='text-2xl font-semibold text-gray-800 dark:text-gray-200'>Details</h1>  
            <FontAwesomeIcon 
              onClick={() => setShowDetails(false)}
              icon={faXmark}
              className="text-xl text-gray-800 transition-colors duration-200 cursor-pointer hover:text-red-500 dark:text-gray-200"
            />
          </div>
          
          {showDetails && selectedFile && (
            <div>
              {/* File Name */}
              <div className='flex flex-row items-center gap-3 my-5'>
                <FontAwesomeIcon 
                  icon={displayFileIcon(selectedFile.name || selectedFile.docName)} 
                  className={`p-3 text-3xl border border-gray-500 shadow-md rounded-xl ${
                    selectedFile.type === "file" || selectedFile.docName ? 'text-red-500' : 'text-blue-500'
                  }`}
                />
                
                {/* Display File Name */}
                <div className="text-gray-800 dark:text-gray-200">              
                  <h2 className="text-xl font-medium ">
                    {(selectedFile.name || selectedFile.docName || selectedFile.meta?.name)?.split(/(_|-)/g).map((part, i) => (
                      (part === '_' || part === '-') 
                        ? <span key={i}>{part}<wbr/></span>
                        : <span key={i}>{part}</span>
                    ))}
                  </h2>
                  
                   {/* Show doc ID for filtered docs */}
                  {selectedFile.docID && (
                    <p className="text-sm text-gray-500 dark:text-gray-400">Document ID: {selectedFile.docID}</p>
                  )}

                  {/* Show mime type for directory files */}
                  {selectedFile.mime && (
                    <p className="text-sm text-gray-500 dark:text-gray-400">{selectedFile.mime.split('/')[1].toUpperCase()} File</p>
                  )}                
                 
                </div>
              </div>
              
              {/* File Details */}            
              <div className="px-2 pt-5 text-gray-800 border-t border-gray-700 dark:text-gray-200">
                
                {/* Directory file details */}
                {selectedFile.size !== undefined && selectedFile.type !== "folder" && (
                  <>
                    <h2 className="mb-2 text-lg font-medium">File Size:</h2>
                    <p className="mb-5 ml-3 text-gray-600 text-md dark:text-gray-400">
                      {formatSize(selectedFile.size)}
                    </p>
                    <h2 className="text-lg font-medium">Modified:</h2>
                    <p className="mb-5 ml-3 text-gray-600 text-md dark:text-gray-400">
                      {selectedFile.modified}
                    </p>

                    {/* Show tags for directory files */}
                                  
                    <h2 className="mb-2 text-lg font-medium">Tags:</h2>
                    <div className="flex flex-wrap gap-2 mb-5 ml-3">
                      {selectedFile.docTag.map((tag, index) => (
                        <span
                          key={index}
                          className="px-2 py-1 text-xs text-gray-700 capitalize border rounded-full border-neutral-400 dark:text-white dark:border-gray-500"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  </>
                )}

                  
                
                
                {/* Folder details */}
                {selectedFile.type === "folder" && (
                  <>
                    <h2 className="mb-2 text-lg font-medium">Folder Size:</h2>
                    <p className="mb-5 ml-3 text-gray-600 text-md dark:text-gray-400">
                      {formatSize(getFolderSize(selectedFile))}
                    </p>
                    <h2 className="text-lg font-medium">Modified:</h2>
                    <p className="mb-5 ml-3 text-gray-600 text-md dark:text-gray-400">
                      {selectedFile.meta.modified}
                    </p>  
                  </>
                )}
                
                {/* Filtered document details */}
                {selectedFile.docPath && (
                  <>
                    <h2 className="mb-2 text-lg font-medium">Document Path:</h2>
                    <p className="mb-5 ml-3 text-sm text-gray-600 break-all dark:text-gray-400">
                      {selectedFile.docPath.replace('UDMS_Repository/', '')}
                    </p>
                  </>
                )}
                
                
              </div>
            </div>
          )}
        </div>
      </div>
        
    </div>   
             
    </>
  );
};

export default Documents;