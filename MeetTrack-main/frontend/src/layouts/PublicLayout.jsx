import { Outlet } from "react-router-dom";
import PublicNavbar from "../components/PublicNavbar";

export default function PublicLayout() {
  return (
    <div className="min-h-screen" style={{ background: "#07090f" }}>
      <PublicNavbar />
      <Outlet />
    </div>
  );
}
