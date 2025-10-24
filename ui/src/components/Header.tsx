import React from 'react';

interface HeaderProps {
  glassStyle: string;
}

const Header: React.FC<HeaderProps> = ({ }) => {
  return (
    <div className="relative mb-16">
      <div className="text-center pt-4 flex flex-col items-center">
        <img
          src="https://i.imgur.com/93XnQfJ.png"
          alt="Sollea Logo"
          width={100}
          height={100}
          className="object-contain mb-4"
        />
        <h1 className="text-[48px] font-medium text-[#1a202c] font-['DM_Sans'] tracking-[-1px] leading-[52px] text-center antialiased">
          Agent de recherche d’entreprise
        </h1>
        <p className="text-gray-600 text-lg font-['DM_Sans'] mt-4">
          Menez une analyse approfondie de l’entreprise
        </p>
      </div>
    </div>
  );
};

export default Header;
