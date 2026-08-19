import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "./components/ui/sonner";
import { AuthProvider, useAuth, roleHome } from "./context/AuthContext";

// Pages
import LandingPage from "./pages/LandingPage";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import DashboardPage from "./pages/DashboardPage";
import JobsPage from "./pages/JobsPage";
import PermitsPage from "./pages/PermitsPage";
import BillingPage from "./pages/BillingPage";
import AdminDashboardPage from "./pages/AdminDashboardPage";
import TipPage from "./pages/TipPage";
import RatePage from "./pages/RatePage";
import ForgotPasswordPage from "./pages/ForgotPasswordPage";
import ResetPasswordPage from "./pages/ResetPasswordPage";
import FacilityHomePage from "./pages/FacilityHomePage";
import DispatchHomePage from "./pages/DispatchHomePage";
import OnboardingPage from "./pages/OnboardingPage";
import ActiveDeliveryPage from "./pages/ActiveDeliveryPage";

// Protected Route Component (kept for generic authed pages)
// eslint-disable-next-line no-unused-vars
const ProtectedRoute = ({ children }) => {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return children;
};

// Public Route - redirect to role home if authenticated
const PublicRoute = ({ children }) => {
  const { isAuthenticated, loading, user } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (isAuthenticated) {
    return <Navigate to={roleHome(user)} replace />;
  }

  return children;
};

// Role Route - requires one of the given roles
const RoleRoute = ({ children, roles }) => {
  const { isAuthenticated, loading, user } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (!roles.includes(user?.role)) return <Navigate to={roleHome(user)} replace />;

  return children;
};

// Verified Driver Route - drivers must be verification-approved; admins pass through
const VerifiedDriverRoute = ({ children }) => {
  const { isAuthenticated, loading, user } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (user?.role === 'driver' && user?.verification_status !== 'approved') {
    return <Navigate to="/onboarding" replace />;
  }
  if (!['driver', 'admin'].includes(user?.role)) return <Navigate to={roleHome(user)} replace />;

  return children;
};

// Admin Route - requires admin role
const AdminRoute = ({ children }) => {
  const { isAuthenticated, loading, user } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (user?.role !== 'admin') return <Navigate to={roleHome(user)} replace />;

  return children;
};

function AppRoutes() {
  return (
    <Routes>
      {/* Public Routes */}
      <Route path="/" element={<LandingPage />} />
      <Route path="/tip/:jobId" element={<TipPage />} />
      <Route path="/rate/:jobId" element={<RatePage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route 
        path="/login" 
        element={
          <PublicRoute>
            <LoginPage />
          </PublicRoute>
        } 
      />
      <Route 
        path="/register" 
        element={
          <PublicRoute>
            <RegisterPage />
          </PublicRoute>
        } 
      />
      
      {/* Protected Routes */}
      <Route 
        path="/onboarding" 
        element={
          <RoleRoute roles={['driver']}>
            <OnboardingPage />
          </RoleRoute>
        } 
      />
      <Route 
        path="/dashboard" 
        element={
          <VerifiedDriverRoute>
            <DashboardPage />
          </VerifiedDriverRoute>
        } 
      />
      <Route 
        path="/jobs" 
        element={
          <VerifiedDriverRoute>
            <JobsPage />
          </VerifiedDriverRoute>
        } 
      />
      <Route 
        path="/delivery/:jobId" 
        element={
          <VerifiedDriverRoute>
            <ActiveDeliveryPage />
          </VerifiedDriverRoute>
        } 
      />
      <Route 
        path="/permits" 
        element={
          <RoleRoute roles={['driver', 'admin']}>
            <PermitsPage />
          </RoleRoute>
        } 
      />
      <Route 
        path="/billing" 
        element={
          <RoleRoute roles={['driver', 'admin']}>
            <BillingPage />
          </RoleRoute>
        } 
      />
      <Route 
        path="/facility" 
        element={
          <RoleRoute roles={['facility', 'admin']}>
            <FacilityHomePage />
          </RoleRoute>
        } 
      />
      <Route 
        path="/dispatch" 
        element={
          <RoleRoute roles={['dispatcher', 'admin']}>
            <DispatchHomePage />
          </RoleRoute>
        } 
      />
      <Route 
        path="/admin" 
        element={
          <AdminRoute>
            <AdminDashboardPage />
          </AdminRoute>
        } 
      />

      {/* Catch all - redirect to landing */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
        <Toaster position="top-right" richColors />
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
