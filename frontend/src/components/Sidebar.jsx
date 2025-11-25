import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { 
    faAngleRight,
    faAngleLeft,
    faSearch,
    faCircleNotch
    } 
from '@fortawesome/free-solid-svg-icons';
import udmsLogo from '../assets/udms-logo.png';
import { createContext, useState, useContext } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useEffect} from 'react';
import { apiGet } from '../utils/api_utils';

export const SidebarContext = createContext();
    const Sidebar = ({children}) => {
	const [expanded, setExpanded] = useState(false);
    const [query, setQuery] = useState("");
    const [results, setResults] = useState([]);
    const [loading, setLoading] = useState(false);
    const [directory, setDirectory] = useState(null);
    const navigate = useNavigate();

    // Detect screen size if viewport is large enough for sidebar to expand at start
    const isLargeScreen = window.matchMedia('(min-width: 1024px)').matches; // Check if the screen is large enough for sidebar expansion

    // Expanded is true if isLargeScreen is true
    useEffect(() => {
        setExpanded(isLargeScreen);
    }, [isLargeScreen]);

    
    // Fetch directory structure for navigation
    useEffect(() => {
        const fetchDirectory = async () => {
            try {
                const res = await apiGet('/api/documents');
                setDirectory(res.data);
            } catch (err) {
                console.error("Failed to fetch directory:", err);
            }
        };
        fetchDirectory();
    }, []);

    
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
        e.preventDefault()
        if(!query.trim()) return
        try{
            const res = await apiGet(`/api/search?q=${encodeURIComponent(query)}`)     
            Array.isArray(res.data) ? setResults(res.data) : setResults([])
            console.log(res.data)
			} catch(err){console.error("Search failed: ", err)}
      }

      
  const handleResultClick = (doc) => {
     if (!directory) {
            console.warn("Directory not loaded yet");
            return;
        }

        let pathArray = doc.docPath.split('/').filter(Boolean);
        
        if(pathArray.length > 0 && pathArray[0] === "UDMS_Repository"){
            pathArray = pathArray.slice(1);
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



    navigate('/Documents', {
        state: {
            navigateToFile: {
                currentPath: filePath,
                expandedFolders: folderPaths,
                highlightedFile: doc.docID
            }
        }
    });

    setQuery("");
    
  }


   // Sidebar component with state for expanded/collapsed
   return(
      <>
		<aside className={`absolute lg:relative row-span-5 h-screen mt-0 lg:mt-3 ml-0 lg:ml-3 transition-all duration-500 ${ expanded ? 'w-70' : 'hidden lg:block w-13'} z-40`}>
			<nav className={`${expanded ? '' : 'hidden lg:block'} min-h-[625px] relative flex flex-col bg-gray-200 border-1 border-neutral-600 dark:border-neutral-500 rounded-lg shadow-lg transition-all duration-500 inset-shadow-sm inset-shadow-gray-400 dark:shadow-md dark:shadow-zuccini-800 dark:bg-gray-900`}>
				{/* Title and Logo */}
				<div className={`flex items-center justify-between pt-3 pb-2 ${expanded ? 'pr-10 pl-2' : 'pl-1'}  transition-all duration-500`}>
					<img src={udmsLogo} alt="UDMS Logo" className={`${expanded ? 'm-2' : ''} h-10 rounded-full w-10 transition-all duration-500`}/>
					<h4 className={`overflow-hidden transition-all m-1 line-clamp-2 font-semibold text-neutral-950 ${expanded ? 'w-42 opacity-100 ml-2' : 'w-0 opacity-0 ml-0'} dark:text-white transition-all duration-500`}>University Document Management System</h4>
					
				</div>

				{/* Search bar*/}
				<div className='relative'>
					<div className="relative px-1 py-2 ml-1 overflow-hidden">
						<FontAwesomeIcon icon={faSearch} className={`absolute text-zuccini-800 ml-3.5 mt-3.5 ${expanded ? '' : 'cursor-pointer'}`} />
						<input type="text" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search..."
							onKeyDown={(e) => {
								if (e.key === "Enter") handleSearch(); // trigger search on Enter key
							}}
							className={`min-w-65 p-2 pl-10 text-gray-800 dark:text-gray-200 placeholder-neutral-400 rounded-xl bg-gray-300 border dark:bg-gray-950 dark:border-gray-800 border-gray-900 transition-colors duration-500 focus:outline-none focus:ring-2 focus:ring-zuccini-900 ${expanded ? '' : 'cursor-pointer'} dark:border-neutral-800 dark:bg-[#242424]`}
						/>
					</div>
				
	
						{/* Search results */}
					{query.trim() !== "" && (
						<ul className="absolute z-10 w-full max-w-[300px] p-2 pt-3 overflow-y-scroll border border-gray-300 right-0 top-full bg-gray-100/50 backdrop-blur-sm rounded-b-xl text-neutral-800 dark:text-white dark:border-gray-900 dark:bg-gray-800/20 max-h-72 ">
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


					{/* Nav Links */}
					<SidebarContext.Provider value={{expanded}}>
					<ul className={`flex flex-col gap-y-4 py-1 flex-1 ml-1 mt-1 ${expanded ? 'items-end' : ''}`}>{children}</ul> 
					</SidebarContext.Provider>
					{/* SidebarLinks is are generated below */}

			</nav>
		</aside>

		<button onClick={() => setExpanded(current => !current)} className={`${expanded ? 'left-65 md:left-67 md:top-8 z-50 ' : 'left-2 md:top-[5%] md:left-[1.2%] z-60'} hover:scale-110 cursor-pointer top-4 absolute p-2 px-4 md:transition-all duration-500 active:scale-90 rounded-lg bg-zuccini-900`}>
				{ expanded ? <FontAwesomeIcon icon={faAngleLeft} /> : <FontAwesomeIcon icon={faAngleRight} /> }
		</button>
      </>
   );
    
};

export const SidebarLinks = ({children, icon, text, active, alert, onClick, isButton}) => {
  const {expanded} = useContext(SidebarContext);
  

  //Sidebar Contents
  const content = (
    <>
      <span className={`${expanded ? 'ml-2 mr-3' : 'mx-auto'} ${active ? 'text-white' : 'text-zuccini-800'} transition-all duration-500 flex-shrink-0`}>
          <FontAwesomeIcon icon={icon} className='mr-1 text-center transition-all duration-500 shadow-xl' />
      </span>

      <span className={`text-[15px] transition-all duration-500 whitespace-nowrap overflow-hidden ${expanded ? 'w-32 opacity-100 ml-1' : 'w-0 opacity-0 ml-0'} dark:text-white`}>{text}</span>

      {alert && (
      <span className={`absolute right-3 bg-zuccini-900 px-1.5 py-1.5 shadow-lg rounded-full transition-all duration-500 ${expanded ? 'top-3.5' : 'top-2'}`}>{alert}</span>)}
        
        {children && <span className={`ml-auto overflow-hidden transition-all duration 500 ${expanded ? 'w-11' : 'w-0'}`}>{children}</span>}
      
        {/* Labels for sections when sidebar is collapsed */}
      {!expanded && <div className="absolute invisible px-2 py-1 ml-6 text-sm font-bold text-center transition-all -translate-x-3 rounded-md shadow-lg left-full w-30 bg-zuccini-600 text-neutral-200 opacity-20 duration 500 group-hover:visible group-hover:opacity-100 group-hover:translate-x-0">{text}</div>}

    </>
);

    return isButton ? (
            <li className="relative flex items-center text-neutral-800 text-shadow-lg transition-all duration-500 min-h-[42px] group cursor-pointer">
            <div  
                onClick={onClick}
                 className={`flex items-center mb-0.5 py-2 px-0.5 text-xl rounded-l-xl font-semibold hover:bg-gray-400 dark:hover:bg-gray-950 ease-in-out transition-all duration-500 ${expanded ? 'w-65' : 'w-12'}`}>
                 {content}
            </div>
            </li>
         
        ): (
            <li className="relative flex items-center text-shadow-lg transition-all duration-500 min-h-[42px] group cursor-pointer">
             <Link to={`/${text}`} onClick={onClick} className={`flex items-center mb-0.5 py-2 px-0.5 text-xl rounded-l-xl text-neutral-800 font-semibold hover:bg-gray-400 dark:hover:bg-gray-950 ease-in-out transition-all duration-500 ${expanded ? 'w-65' : 'w-12'} ${active ? 'bg-zuccini-800 text-white hover:bg-zuccini-900 dark:hover:bg-zuccini-900' : ''}`}>
                 {content}
             </Link>
            </li>

    );
};




export default Sidebar;