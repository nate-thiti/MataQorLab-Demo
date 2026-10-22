// @ts-nocheck
const PageWrapper = ({ children, disableBlobs = false }) => {
  return (
    <div className="relative min-h-screen">
      {!disableBlobs && (
        <div className="liquid-bg-container">
          <div className="liquid-blob blob-1"></div>
          <div className="liquid-blob blob-2"></div>
          <div className="liquid-blob blob-3"></div>
          <div className="liquid-blob blob-4"></div>
        </div>
      )}

      <div className="relative">
        {children}
      </div>
    </div>
  );
};

export default PageWrapper;
