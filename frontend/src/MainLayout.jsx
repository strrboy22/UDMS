import { useState, useEffect} from 'react';
import { useLocation, Outlet, useNavigate } from 'react-router-dom';

//Importing Components
import './App.css'
import Sidebar, { SidebarLinks } from './components/Sidebar';
import Switch from './components/Switch';
import Header from './components/Header';
import logOut from './assets/log_out.svg';
//Importing  Icons
import{
  faLayerGroup, 
    faSchool, 
    faGraduationCap, 
    faUsers, 
    faCircleCheck, 
    faFileAlt, 
    faMoon,
    faIdCardClip,
    faArrowRightFromBracket,
    faPenFancy
} from '@fortawesome/free-solid-svg-icons';
import { getCurrentUser, adminHelper } from './utils/auth_utils';
import { apiPost } from './utils/api_utils';
import { getSocket, resetPresenceListeners } from './utils/websocket_utils';


const MainLayout = () => {
  //sets the active pages' path in the link
  const location = useLocation();
  const activePage = location.pathname.replace('/','') || 'Dashboard';
  const isAdmin = adminHelper()
  const user = getCurrentUser()

  //toggles Dark Mode
  const [darkMode, setDarkMode] = useState(() =>{
    return localStorage.getItem('darkMode') ===  "true"; 
  });
  useEffect( () => {
    if(darkMode){
      document.documentElement.classList.add('dark');
    }else{
      document.documentElement.classList.remove('dark');
    }

    localStorage.setItem('darkMode', darkMode)
  }, [darkMode])

    //Log out logic
  const [showLogout, setShowLogout] = useState(false);
  const navigate = useNavigate()
  //shows the logout confirmation
  const loginCancel = () =>{
    setShowLogout(false)
  }

  return(
    <>
    <div className="grid grid-cols-[auto_1fr] grid-rows-[100px_1fr] h-screen w-screen bg-neutral-200 relative dark:bg-gray-950">
          <Sidebar>      
                <SidebarLinks
                  icon={faLayerGroup}
                  text="Dashboard"
                  active={activePage === 'Dashboard'}
                  onClick={() => navigate('/Dashboard')}
                />               
                <SidebarLinks
                  icon={faGraduationCap}
                  text="Programs"
                  active={activePage === 'Programs'}
                  onClick={() => navigate('/Programs')}
                />
                { (isAdmin || user.isRating) && (<SidebarLinks
                  icon={faIdCardClip}
                  text="Accreditation"
                  active={activePage === 'Accreditation'}
                  onClick={() => navigate('/Accreditation')}
                />)}
                { (isAdmin || user.isEdit) && (<SidebarLinks
                  icon={faUsers}
                  text="Users"
                  active={activePage === 'Users'}
                  onClick={() => navigate('/Users')}
                />)}
                { isAdmin && (<SidebarLinks
                  icon={faPenFancy}
                  text="Templates"
                  active={activePage === 'Templates'}
                  onClick={() => navigate('/Templates')}
                />)}          
                <SidebarLinks
                  icon={faFileAlt}
                  text="Documents"
                  active={activePage === 'Documents'}
                  onClick={() => navigate('/Documents')}
                />

              <hr className="w-full my-3 border-x border-neutral-400 dark:border-neutral-800" />

              {/* Dark Mode and Log out */}
              <SidebarLinks icon={faMoon} text="Dark Mode" isButton> 
                <Switch isChecked={darkMode} onChange={() => {setDarkMode ((current) => !current)}}/>
              </SidebarLinks> 
              <SidebarLinks icon={faArrowRightFromBracket} onClick={() => {setShowLogout(true)}} text="Log Out" isButton/>                
          </Sidebar>
            
          
          
          {/* Main Content */}

          <main id="main-scroll" className="relative flex-1 h-full col-span-4 col-start-2 row-span-5 row-start-1 p-4 overflow-y-auto">
            <Header title={activePage} />
            <Outlet />
          </main>
         
      </div>
      
      {showLogout && (
        <div className="fixed inset-0 z-50 flex items-center justify-center transition-all duration-500 bg-neutral-900/50">
          <div className="flex flex-col items-center justify-center p-6 bg-gray-200 rounded-2xl shadow-xl border-2 border-neutral-700 transition-all duration-500 dark:inset-shadow-sm dark:inset-shadow-zuccini-900 dark:border-none dark:bg-gray-800 min-h-[55%] min-w-[50%]">
            <h1 className='mb-5 text-4xl font-semibold text-zuccini-500'>Logout</h1>
            <img src={logOut} alt="Log out illustration" 
              className='h-40 mb-2'
            />
            <h1 className="mb-10 text-2xl font-semibold text-center text-black text-shadow-sm dark:text-white">
              Are you sure you want to Log Out?
            </h1>
            <div className="flex justify-center space-x-[50px]">
                             <button onClick={ async () => {
                 const sessionId = localStorage.getItem('session_id')
                 
                 // Close logout modal first
                 setShowLogout(false)
                 
                 // Send session ID to backend (employeeID is optional now)
                 await apiPost('/api/logout', { 
                   session_id: sessionId, 
                   employeeID: user?.employeeID || null
                 })
                 
                 // Clear frontend storage
                 localStorage.removeItem('session_id')
                 sessionStorage.removeItem('user')
                 sessionStorage.removeItem('LoggedIn')
                 sessionStorage.removeItem('welcomeShown')
                 for (const k of Object.keys(sessionStorage)) {
                  if (k.startsWith('welcomeShown:')) sessionStorage.removeItem(k)
                }

                 //disconnect to websocket
                 const socket = getSocket()
                 resetPresenceListeners()
                 socket.removeAllListeners?.()
                 socket.disconnect()
                 socket.off('users_online')
                 
                 
                 // Broadcast logout to other tabs
                 const ch = new BroadcastChannel('auth')
                 const payload = {type: 'logout', ts: Date.now()}
                 ch.postMessage(payload)
                 ch.close()
                 
                 // Navigate to login
                 navigate('/login', {replace: true})
               }} className="shadow-xl px-4 py-2 transition-all duration-300 text-white cursor-pointer w-[150px] rounded-2xl bg-zuccini-600 hover:bg-zuccini-700">Log out</button>
              <button onClick={loginCancel} className="shadow-xl transition-all duration-300 px-4 py-3 w-[150px] text-white cursor-pointer rounded-2xl bg-zuccini-600 hover:bg-zuccini-700">Cancel</button>
            </div>
          </div>
        </div>
      )}

    </>
  )
}

export default MainLayout;